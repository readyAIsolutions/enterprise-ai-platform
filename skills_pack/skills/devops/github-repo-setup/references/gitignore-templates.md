# .gitignore Templates by Language/Framework

## Python (Comprehensive)
```gitignore
# Python bytecode
__pycache__/
*.py[cod]
*$py.class

# Virtual environments
venv/
env/
.venv/
ENV/

# Environment files
.env
.env.local
.env.*.local
*.env

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Logs
*.log
logs/
*.out

# Build artifacts
dist/
build/
*.egg-info/
*.whl
*.egg
pip-wheel-metadata/

# Test artifacts
.coverage
htmlcov/
.pytest_cache/
.mypy_cache/
.tox/
.nox/
.hypothesis/

# Type checking
*.pyc
*.pyo
*.pyd

# Distribution
*.tar.gz
*.zip

# Documentation
docs/_build/
site/

# Jupyter
.ipynb_checkpoints/
*.ipynb

# PyInstaller
*.manifest
*.spec

# Unit test / coverage
htmlcov/
.coverage.*
coverage.xml
*.cover
.hypothesis/

# Translations
*.mo
*.pot

# Django
*.log
local_settings.py
db.sqlite3
db.sqlite3-journal
media/

# Flask
instance/
.webassets-cache

# Scrapy
.scrapy/

# Sphinx
docs/_build/

# PyBuilder
target/

# IPython
profile_default/
ipython_config.py

# pdm
.pdm.toml

# PEP 582
__pypackages__/

# Celery
celerybeat-schedule
celerybeat.pid

# SageMath
*.sage.py

# Environments
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# Spyder
.spyderproject
.spyproject

# Rope
.ropeproject

# mkdocs
site/

# mypy
.mypy_cache/
.dmypy.json
dmypy.json

# Pyre
.pyre/

# pytype
.pytype/

# Cython
*.c
*.so
```

## Node.js
```gitignore
# Dependencies
node_modules/
jspm_packages/

# Build
dist/
build/
*.tsbuildinfo

# Environment
.env
.env.local
.env.*.local

# Logs
*.log
npm-debug.log*
yarn-debug.log*
yarn-error.log*
pnpm-debug.log*
lerna-debug.log*

# Testing
coverage/
.nyc_output/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Turbo
.turbo/

# Vercel
.vercel

# Next.js
.next/
out/

# Vite
*.local
```

## Docker
```gitignore
# Docker
.dockerignore
docker-compose.override.yml

# Build secrets
*.key
*.pem
*.crt
secrets/
```

## Go
```gitignore
# Binaries
*.exe
*.exe~
*.dll
*.so
*.dylib
*.test
*.out

# Dependency directories
vendor/

# Build
*.o
*.a

# Test
*.prof
```

## Rust
```gitignore
# Build
target/
**/*.rs.bk

# Cargo
Cargo.lock

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
```

## Java (Maven/Gradle)
```gitignore
# Build
target/
build/
*.class
*.jar
*.war
*.ear
*.nar

# IDE
.idea/
*.iml
*.ipr
.vscode/
.classpath
.project
.settings/

# OS
.DS_Store
Thumbs.db

# Logs
*.log

# Gradle
.gradle/
gradlew
gradlew.bat

# Maven
.mvn/
mvnw
mvnw.cmd
```

## Universal Minimal
```gitignore
# OS
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
*.swp
*.swo

# Logs
*.log

# Environment
.env
.env.local

# Build artifacts
dist/
build/
*.egg-info/
```

## Usage
```bash
# Write Python template
cat > .gitignore << 'EOF'
# paste template here
EOF

# Or use gitignore.io API
curl -sL https://www.toptal.com/developers/gitignore/api/python,node,docker,go,rust > .gitignore
```