# GITHUB_REPOS Dataset Schema

## CRITICAL: Database Assignment
- SQLite (repo_metadata.db) = metadata only: languages, repos, licenses
- DuckDB (repo_artifacts.db) = code artifacts: commits, contents, files
- NEVER query "files" or "commits" from SQLite — they do not exist there
- NEVER query "languages", "repos", "licenses" from DuckDB — they do not exist there

## SQLite — repo_metadata.db
Tables: languages, repos, licenses

### languages
- repo_name (TEXT): GitHub repo "owner/repo" e.g. "apple/swift"
- language_description (TEXT): Languages used e.g. "Python, JavaScript"

### repos  
- repo_name (TEXT): GitHub repo "owner/repo"
- watch_count (INTEGER): Number of watchers

### licenses
- repo_name (TEXT): GitHub repo "owner/repo"
- license (TEXT): e.g. "apache-2.0", "mit", "gpl-2.0"

## DuckDB — repo_artifacts.db
Tables: commits, contents, files

### commits
- commit (TEXT): SHA identifier
- subject (TEXT): Short commit message subject line
- message (TEXT): Full commit message
- repo_name (TEXT): GitHub repo "owner/repo"
- author (TEXT): JSON with name, email, timestamp
- difference (TEXT): JSON file changes

### contents
- id (TEXT): File blob identifier
- content (TEXT): File text content
- sample_repo_name (TEXT): GitHub repo "owner/repo"
- sample_path (TEXT): File path e.g. "README.md", "src/main.py"
- sample_symlink_target (TEXT): Symlink target if applicable
- repo_data_description (TEXT): Natural language file metadata

### files
- repo_name (TEXT): GitHub repo "owner/repo"
- ref (TEXT): Branch or commit SHA
- path (TEXT): File path e.g. "README.md"
- mode (INTEGER): File mode
- id (TEXT): File blob identifier
- symlink_target (TEXT): Symlink target if applicable

## Cross-Database Join Pattern
SQLite repo_name = DuckDB repo_name (same "owner/repo" format, direct equality)
Example: SELECT l.repo_name FROM languages l JOIN commits c ON l.repo_name = c.repo_name

## Key Query Patterns for Each Question Type

### Language filter (SQLite):
SELECT repo_name FROM languages WHERE language_description LIKE '%Python%'
SELECT repo_name FROM languages WHERE language_description NOT LIKE '%Python%'
SELECT repo_name FROM languages WHERE language_description LIKE '%Swift%'
SELECT repo_name FROM languages WHERE language_description LIKE '%Shell%'

### License filter (SQLite):
SELECT repo_name FROM licenses WHERE license = 'apache-2.0'

### README files (DuckDB files table):
SELECT DISTINCT repo_name FROM files WHERE path LIKE '%README%'

### Copyright check in README content (DuckDB contents table):
SELECT DISTINCT sample_repo_name FROM contents
WHERE sample_path LIKE '%README%'
AND (content LIKE '%copyright%' OR content LIKE '%Copyright%' OR content LIKE '%(c)%')

### Commit count per repo (DuckDB):
SELECT repo_name, COUNT(*) as num_commits FROM commits GROUP BY repo_name ORDER BY num_commits DESC

### Commit message filter (DuckDB):
WHERE message IS NOT NULL
AND LENGTH(message) < 1000
AND LOWER(message) NOT LIKE 'merge%'
AND LOWER(message) NOT LIKE 'update%'
AND LOWER(message) NOT LIKE 'test%'

### Non-binary Swift files (DuckDB contents):
WHERE sample_path LIKE '%.swift'
AND repo_data_description NOT LIKE '%binary%'
