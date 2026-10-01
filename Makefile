.PHONY: install ui api test seed demo audit
install:
	python -m pip install -U pip
	python -m pip install -e ".[all]"
api:
	uvicorn promisekeeper.api:app --reload --port 8000
ui:
	streamlit run src/promisekeeper/ui.py
test:
	PK_MEMORY_BACKEND=local pytest -q
seed:
	python -m promisekeeper.cli seed
demo:
	python -m promisekeeper.cli demo
audit:
	./audit_submission.sh
