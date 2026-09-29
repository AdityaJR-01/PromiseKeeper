.PHONY: install ui api test audit
install:
	python -m pip install -U pip
	python -m pip install -e ".[all]"
api:
	uvicorn promisekeeper.api:app --reload --port 8000
ui:
	streamlit run src/promisekeeper/ui.py
test:
	PK_MEMORY_BACKEND=local pytest -q
audit:
	@echo "--- prohibited word ---"
	@! grep -rniE 'hack-?a-?thon' README.md docs/ content/ 2>/dev/null || (echo FAIL; exit 1)
	@echo "--- tracked .env ---"
	@! git ls-files | grep -E '(^|/)\.env$$' || (echo FAIL; exit 1)
	@echo "AUDIT OK"
