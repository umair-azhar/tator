lint:
	@./pylint_wrapper.sh pytator ingestor.py

.PHONY: dist
dist: 
	pyinstaller -F --icon cvision_no_text.ico -n importer ingestor.py
	mv importer.spec build

.PHONY: wheel
wheel:
	rm -fr build
	python3 setup.py bdist_wheel

.PHONY: install
install:
	pip3 install .
#Hack to fix shebang in local lines
	cp tator_testHarness.py `which tator_testHarness.py`

