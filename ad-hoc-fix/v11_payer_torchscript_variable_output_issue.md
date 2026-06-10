# TorchScript Variable-Length Output Issue in `deploy_v2.py`

## Background

The `payer-model-v3` branch introduced an optional payer head (`main_payer_d7`) for user value models.
To support this, `run_forward_and_post_process` in `deploy_v2.py` was updated to conditionally return
either 23 outputs (non-payer models) or 24 outputs (payer models, with `payer_d7_prob` appended):

```python
if nn_output.shape[1] >= 15:
    outputs = base_outputs + (payer_d7_prob,)   # 24-tuple
    ...
    return outputs

return base_outputs                              # 23-tuple
```

This works correctly at runtime for AOT-compiled models (`optimize_mode=torch_aot`), where the model
binary is pre-compiled and the conditional is evaluated during training/export, not at script time.

## Problem: TorchScript Compilation Failure

Models using `optimize_mode=NONE` (e.g. `v8_uasdk_v5`) are deployed via `torch.jit.script`, which
compiles the `DeployModel` class at deploy time. TorchScript performs **static type inference** — it
infers the return type of a function from its first return statement and requires **all** return paths
to return the same type.

Since `run_forward_and_post_process` returns either a `Tuple[Tensor x 24]` or a `Tuple[Tensor x 23]`
depending on a runtime condition, TorchScript raises:

```
RuntimeError:
Previous return statement returned a value of type
    Tuple[Tensor, Tensor, ..., Tensor]  (24 elements)
but this return statement returns a value of type
    Tuple[Tensor, Tensor, ..., Tensor]  (23 elements)

File "deploy_v2.py", line 344
    stacked_outputs = torch.stack(base_outputs)
    ...
    return (padded_outputs[0], ..., padded_outputs[22])   # <-- HERE
```

### Why AOT models are unaffected

AOT compilation (`torch.compile` / `torch._export`) traces the model with concrete example inputs.
Only the branch actually executed during tracing is compiled into the binary — the return type
inconsistency is never checked. JIT script compilation, by contrast, must type-check the entire
function body statically.

### Why `OUTPUT_MAP` cannot be used as a workaround

Changing `OUTPUT_MAP` to conditionally return 23 or 24 entries based on whether the experiment has
a payer head would fix the Triton `config.pbtxt` generation, but would break serving for any
existing deployed model version that was compiled against the old (24-entry) output contract.
The output map must remain stable across model versions for a given experiment.

## Affected Experiments

Any user value experiment that:
1. Uses `optimize_mode=NONE` (i.e. deploys via `torch.jit.script`), **and**
2. Does **not** have `main_payer_d7` in its `nn_config.model.heads`

will fail at deploy time with the above TorchScript error after the `payer-model-v3` branch is merged.

---

## Proposed Solution: Separate `DeployModel` and `PayerDeployModel` Classes

Split the payer and non-payer logic into two distinct classes, each with a **single consistent return
type**. TorchScript compiles each class independently, so it never sees conflicting return types.

### Class structure

```
DeployModel          — non-payer; run_forward_and_post_process always returns 23-tuple
  └── DeployModel_Aot       — AOT wrapper for non-payer (unchanged forward() signature)

PayerDeployModel(DeployModel)
  — payer; run_forward_and_post_process always returns 24-tuple
  └── PayerDeployModel_Aot  — AOT wrapper for payer
```

### `deploy_v2.py` changes

**`DeployModel.run_forward_and_post_process`** — remove the `if nn_output.shape[1] >= 15` output
split; always build and return `base_outputs` (23 elements):

```python
class DeployModel(UnityLearnerDeployModel):
    def run_forward_and_post_process(self, inputs):
        ...
        # Retention logic unchanged (optional, checked by shape)
        ...
        base_outputs = (p, non_log_value, ..., ret_d7_prob)  # always 23

        if self.use_request_batching:
            stacked_outputs = torch.stack(base_outputs)
            padded_outputs = pad_and_reshape_outputs(...)
            return (padded_outputs[0], ..., padded_outputs[22])  # always 23
        return base_outputs
```

**`PayerDeployModel(DeployModel)`** — override `run_forward_and_post_process`; always includes
payer logic and returns 24-tuple:

```python
class PayerDeployModel(DeployModel):
    def run_forward_and_post_process(self, inputs):
        ...
        # Same pricing logic as DeployModel, plus:
        payer_prob_d7 = nn_output[:, 14].view(-1)
        ...
        base_outputs = (p, non_log_value, ..., ret_d7_prob, payer_prob_d7)  # always 24

        if self.use_request_batching:
            stacked_outputs = torch.stack(base_outputs)
            padded_outputs = pad_and_reshape_outputs(...)
            return (padded_outputs[0], ..., padded_outputs[23])  # always 24
        return base_outputs
```

**`DeployModel_Aot`** — unchanged, continues to extend `DeployModel`.

**`PayerDeployModel_Aot(PayerDeployModel)`** — new AOT wrapper for payer experiments:

```python
class PayerDeployModel_Aot(PayerDeployModel):
    def __init__(self, model, config, trained_model=None, sample_batch=None):
        super().__init__(model, config, trained_model, sample_batch)
        assert self.use_static_shape, "Static shape is required for PayerDeployModel_Aot"

    def forward(self, inputs: list[torch.Tensor]):
        inputs = unpack_tensor_list_static_shape(...)
        return self.run_forward_and_post_process(inputs)
```

### Experiment `model.py` changes

Payer experiments (e.g. `v11_payer_v3`) update their `model.py` to import the payer deploy class:

```python
# Before
from unity_learner.deploy.user_value.deploy_v2 import DeployModel_Aot as BaseDeployModel

# After
from unity_learner.deploy.user_value.deploy_v2 import PayerDeployModel_Aot as BaseDeployModel
```

Non-payer experiments (e.g. `v8_uasdk_v5`, `v14_q2a`) are unchanged — they already import
`DeployModel` / `DeployModel_Aot`.

### Why this is correct

- Each class has a **fixed, known return type** at TorchScript compile time — no conditional splits.
- `OUTPUT_MAP` / `BASE_OUTPUT_MAP` and the `get_output_map(config)` function remain stable.
  Non-payer experiments produce 23 outputs; payer experiments produce 24. The Triton `config.pbtxt`
  continues to be generated correctly from the config-aware `get_output_map`.
- No behavior change for any existing deployed model version.
- The payer/non-payer boundary is explicit at the class level rather than hidden in a runtime branch.

### Files to change

| File | Change |
|---|---|
| `src/unity_learner/deploy/user_value/deploy_v2.py` | Add `PayerDeployModel` and `PayerDeployModel_Aot`; remove payer conditional from `DeployModel.run_forward_and_post_process` |
| `src/unity_learner/experiment_repo/unified_user_value/<payer_exp>/model.py` | Import `PayerDeployModel_Aot` instead of `DeployModel_Aot` |
| `test/unity_learner/util/test_triton_util.py` | Add payer experiment to the parametrized output test if needed |
