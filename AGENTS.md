# Repository Agent Instructions

## Git and generated files

- Never commit Playwright browsers, browser profiles, virtual environments,
  `node_modules`, build output, downloaded binaries, databases, or runtime logs.
- Do not use `git add -A` or `git add .` before inspecting `git status`. Stage
  only the files needed for the task.
- Before committing, run `git diff --cached --stat` and run the Git hygiene
  guard with `python3 scripts/check_git_file_sizes.py staged`.
- A single staged file must stay below 20 MB; staged content must stay below
  50 MB. Pushed history must stay below 100 MB of newly introduced blobs.
- Generated runtime assets belong under `COW_DATA_DIR` or an external release,
  not in Git. Do not add Git LFS for browser caches or virtual environments.
- Deleting a large file in a later commit does not remove the blob from
  history. Rewrite unpushed commits before pushing if a large blob was already
  committed.

## Native macOS operations

- Follow `docs/native-macos-devops-manual.md` for installation, testing,
  launchd operations, backups and large-file history recovery.
