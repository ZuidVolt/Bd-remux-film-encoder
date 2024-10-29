
run:
	python3 main.py

run-pypy:
	pypy3 main.py

check:
	ruff format --line-length 120 .
	ruff check --extend-select F,W,N,C90,B,UP,RET,SIM,RUF,NPY,PD,ARG,TCH,TID,PTH,Q,ISC,PIE,YTT,ASYNC,C4,T10 --fix --unsafe-fixes --ignore "PD901,C901" .
	mypy --check-untyped-defs .