
run:
	python3 main.py

run-pypy:
	pypy3 main.py

# main check (Enforced before commit)
check:
	ruff format --line-length 120 .
	ruff check --extend-select F,W,N,C90,B,UP,RET,SIM,RUF,NPY,PD,ARG,TCH,TID,PTH,Q,ISC,PIE,YTT,ASYNC,C4,T10,A,COM,RSE,E --fix --unsafe-fixes --ignore "PD901,C901,PTH109,E501" .
	mypy --check-untyped-defs .
	pyright .

# Additional analysis checks (not Enforced)

coverage:
	coverage run -m pytest
	coverage report -m
	coverage html

security:
	ruff check --extend-select S --fix

radon: # cyclomatic complexity (exlude venv and archive)
	find . -type f -name "*.py" ! -path "./archive/*" ! -path "./.venv/*" | xargs radon cc -a -nc -s

radon-mi: # maintainability index (exlude venv and archive)
	find . -type f -name "*.py" ! -path "./archive/*" ! -path "./.venv/*" | xargs radon mi -s

vulture: # unused code (exlude venv and archive)
	find . -type f -name "*.py" ! -path "./archive/*" ! -path "./.venv/*" | xargs vulture # --min-confidence 80

pylyzer:
	find . -type f -name "*.py" ! -path "./archive/*" ! -path "./.venv/*" | xargs pylyzer --disable
# Define the target for grepping Python string
gps:
		@grep -r --include="*.py" --exclude-dir=".venv" --exclude-dir="archive" "$(string)" .

# Define a variable for the string to search
string ?= "SideData"
