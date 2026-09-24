CC ?= gcc
CFLAGS ?= -O2 -Wall -Wextra -Iinclude
SRC = src/main.c src/http.c src/net.c src/sync.c

sas-net: $(SRC)
	$(CC) $(CFLAGS) -o $@ $(SRC)

clean:
	rm -f sas-net
