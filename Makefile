# Makefile for shm_rw test programs
CC = gcc
CFLAGS = -Wall -O2 -std=c99
LDFLAGS = -lrt  # For shm_open functions

# Targets
TARGETS = shm_rw shm_rw_fixed_addr

all: $(TARGETS)

shm_rw: shm_rw.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

shm_rw_fixed_addr: shm_rw_fixed_addr.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

clean:
	rm -f $(TARGETS)

.PHONY: all clean test
