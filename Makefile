VIRTUALENV = virtualenv --python=python3
SPHINX_BUILDDIR = docs/_build
VENV := $(shell realpath $${VIRTUAL_ENV-.venv})
PYTHON = $(VENV)/bin/python3
DEV_STAMP = $(VENV)/.dev_env_installed.stamp
DOC_STAMP = $(VENV)/.doc_env_installed.stamp
INSTALL_STAMP = $(VENV)/.install.stamp
TEMPDIR := $(shell mktemp -d)

all: install
install: virtualenv $(INSTALL_STAMP)
$(INSTALL_STAMP):
	$(VENV)/bin/pip install -U pip
	$(VENV)/bin/pip install -r requirements.txt
	touch $(INSTALL_STAMP)

virtualenv: $(PYTHON)
$(PYTHON):
	$(VIRTUALENV) $(VENV)

install-dev: $(INSTALL_STAMP) $(DEV_STAMP)
$(DEV_STAMP): $(PYTHON) dev-requirements.txt
	$(VENV)/bin/pip install -Ur dev-requirements.txt
	touch $(DEV_STAMP)

remove-install-stamp:
	rm $(INSTALL_STAMP)

update: remove-install-stamp install

serve: install
	$(PYTHON) -m ihatemoney.manage runserver

test: $(DEV_STAMP)
	$(VENV)/bin/tox

release: $(DEV_STAMP)
	$(VENV)/bin/fullrelease

build-translations:
	$(VENV)/bin/pybabel compile -d ihatemoney/translations

build-requirements:
	$(VIRTUALENV) $(TEMPDIR)
	$(TEMPDIR)/bin/pip install -U pip
	$(TEMPDIR)/bin/pip install -Ue "."
	$(TEMPDIR)/bin/pip freeze | grep -v -- '-e' > requirements.txt

clean:
	rm -rf .venv
