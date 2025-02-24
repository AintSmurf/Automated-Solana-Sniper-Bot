ifeq ($(OS), Windows_NT)

VENV_DIR=venv

all: install build run clean

run:
	@echo "Running the bot..."
	.\venv\Scripts\activate && python app.py

install:
	@echo "Setting up virtual environment and installing dependencies..."
	if not exist "$(VENV_DIR)" python -m venv $(VENV_DIR)
	.\venv\Scripts\activate && python -m pip install --upgrade pip
	.\venv\Scripts\activate && pip install -r requirements.txt

build:
	@echo "Building the project..."
	.\venv\Scripts\activate && python db_seed.py

clean:
	@echo "Cleaning up..."
	if exist "$(VENV_DIR)" rd /s /q $(VENV_DIR)
	if exist "./build" rd /s /q build
	if exist "./dist" rd /s /q dist
	if exist "./Solana_Sniper.egg-info" rd /s /q Solana_Sniper.egg-info

else

VENV_DIR=venv

all: install build run clean

run:
	@echo "Running the bot..."
	. ./venv/bin/activate && python3 app.py

install:
	@echo "Setting up virtual environment and installing dependencies..."
	sudo apt install -y python3-venv
	if [ ! -d "$(VENV_DIR)" ]; then python3 -m venv $(VENV_DIR); fi
	chmod +x venv/bin/activate  
	. ./venv/bin/activate && python3 -m pip install --upgrade pip
	. ./venv/bin/activate && pip install -r requirements.txt

build:
	@echo "Building the project..."
	. ./venv/bin/activate && python3 db_seed.py 
	. ./Credentials.sh

clean:
	@echo "Cleaning up..."
	. ./venv/bin/activate && python3 reset_db.py
	rm -rf build dist Solana_Sniper.egg-info $(VENV_DIR)
	find . -iname "*.pyc" -delete

endif
