# Skill: Convert Google Doc to GitHub Issue

Convert a Google Doc describing a bug, investigation, or proposal into a well-structured GitHub issue.

---

## Prerequisites

- The Google Doc must be **publicly shared** ("Anyone with the link can view"). Private docs return 401 and cannot be read.
- `gh` CLI must be authenticated (`gh auth status`).

---

## Steps

### 1. Read the Google Doc

Use the export URL pattern to fetch the doc as plain text:

```
https://docs.google.com/document/d/{DOC_ID}/export?format=txt
```

This returns a `307` redirect — follow it to retrieve the content.

### 2. Read the existing GitHub issue (if updating)

```bash
gh issue view {ISSUE_NUMBER} --repo {ORG/REPO}
```

### 3. Write the issue body to a temp file

For complex bodies with backticks and special characters, always write to a temp file and use `--body-file` to avoid shell escaping issues.

```bash
cat > /tmp/issue_body.md << 'EOF'
## Situation
...

## Task
...

## Action
...

## Result
...
EOF
```

### 4. Create or update the issue

**Create:**
```bash
gh issue create \
  --repo {ORG/REPO} \
  --title "{TITLE}" \
  --body-file /tmp/issue_body.md \
  --assignee {USERNAME}
```

**Update:**
```bash
gh issue edit {ISSUE_NUMBER} \
  --repo {ORG/REPO} \
  --body-file /tmp/issue_body.md
```

To also update the title:
```bash
gh issue edit {ISSUE_NUMBER} \
  --repo {ORG/REPO} \
  --title "{NEW_TITLE}" \
  --body-file /tmp/issue_body.md
```

---

## Issue Body Template

```markdown
## Situation
[Describe the current state, what is broken or unclear, and the impact.
Include relevant data points, e.g. "19 out of 365 live campaigns (5.33%) are affected."]

## Task
[What needs to be decided or resolved.]

## Action
[Concrete implementation steps. Be specific — reference field names, services, or components.]

## Result
[Expected outcome after the actions are completed.]
```

---

## Tips

- **Title**: Make the title specific and action-oriented. Avoid vague titles like "Clean up logging" — prefer "Add target_cpe field to distinguish CPE target CPE from max bid cap".
- **Body file**: Always use `--body-file` instead of `--body` when the content contains backticks, newlines, or special characters to avoid shell parsing errors.
- **Google Doc access**: If the doc returns 401, ask the owner to set sharing to "Anyone with the link → Viewer", or paste the content directly.
- **Updating incrementally**: Re-read the current issue body with `gh issue view --json body -q .body` before editing, so context is not lost.
