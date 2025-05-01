ifeq ($(OS), Windows_NT)

VENV_DIR=venv

all: install run

run:
	@echo "Running the bot..."
	.\$(VENV_DIR)\Scripts\activate && python app.py

install:
	@echo "Setting up virtual environment and installing dependencies..."
	if not exist "$(VENV_DIR)" python -m venv $(VENV_DIR)
	.\$(VENV_DIR)\Scripts\activate && python -m pip install --upgrade pip
	.\$(VENV_DIR)\Scripts\activate && pip install -r requirements.txt

test:
	@echo "Running tests..."
	.\$(VENV_DIR)\Scripts\activate && pytest

clean:
	@echo "Cleaning up..."
	if exist "$(VENV_DIR)" rd /s /q $(VENV_DIR)
	if exist "./build" rd /s /q build
	if exist "./dist" rd /s /q dist
	if exist "./Solana_Sniper.egg-info" rd /s /q Solana_Sniper.egg-info

else

VENV_DIR=venv

all: install run

run:
	@echo "Running the bot..."
	. ./$(VENV_DIR)/bin/activate && python3 app.py

install:
	@echo "Setting up virtual environment and installing dependencies..."
	sudo apt install -y python3-venv
	if [ ! -d "$(VENV_DIR)" ]; then python3 -m venv $(VENV_DIR); fi
	chmod +x $(VENV_DIR)/bin/activate
	. ./$(VENV_DIR)/bin/activate && python3 -m pip install --upgrade pip
	. ./$(VENV_DIR)/bin/activate && pip install -r requirements.txt

test:
	@echo "Running tests..."
	. ./$(VENV_DIR)/bin/activate && pytest

clean:
	@echo "Cleaning up..."
	rm -rf build dist Solana_Sniper.egg-info $(VENV_DIR)
	find . -iname "*.pyc" -delete

endif
