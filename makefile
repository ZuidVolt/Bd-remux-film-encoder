PYTHON_FILES := custom_logger.py main.py utils.py video_processor.py


.PHONY: format ruff-check mypy-strict pyright-check check coverage security radon radon-mi vulture

# main check (Enforced before commit)

format:
	ruff format --line-length 120 .

ruff-check:
	ruff check --extend-select F,W,N,C90,B,UP,RET,SIM,RUF,NPY,PD,ARG,TCH,TID,PTH,Q,ISC,PIE,YTT,ASYNC,C4,T10,A,COM,RSE,PL,E,PGH --fix --unsafe-fixes --ignore "PLR0913,PD901,E501,G004,RUF100,PGH003,PLR0911,PLR0912" $(PYTHON_FILES)

mypy-strict:
	mypy --strict $(PYTHON_FILES)

pyright-check:
	pyright $(PYTHON_FILES)

check: format ruff-check mypy-strict pyright-check

# Additional analysis checks (not Enforced)
coverage:
	coverage run -m pytest
	coverage report -m
	coverage html

security:
	ruff check --extend-select S --fix

radon: # cyclomatic complexity
	radon cc -a -nc -s $(PYTHON_FILES)

radon-mi: # maintainability index
	radon mi -s $(PYTHON_FILES)

vulture: # unused code
	vulture $(PYTHON_FILES)
