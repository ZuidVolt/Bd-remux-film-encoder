
run:
	python3 main.py

run-pypy:
	pypy3 main.py

# main check (Enforced before commit)
check:
	ruff format --line-length 120 .
	ruff check --extend-select F,W,N,C90,B,UP,RET,SIM,RUF,NPY,PD,ARG,TCH,TID,PTH,Q,ISC,PIE,YTT,ASYNC,C4,T10 --fix --unsafe-fixes --ignore "PD901,C901,PTH109" .
	mypy --check-untyped-defs .

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