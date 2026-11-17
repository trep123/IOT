CC ?= cc
CFLAGS ?= -O2 -Wall

# 先下载 mongoose.c / mongoose.h 到本目录（见 README）
device_client: device_client.c mongoose.c mongoose.h
	$(CC) $(CFLAGS) -o $@ device_client.c mongoose.c

clean:
	rm -f device_client
