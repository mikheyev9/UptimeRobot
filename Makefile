.PHONY: all prepare run

all: prepare run

prepare:
	chmod +x run_bot.sh

run:
	./run_bot.sh
