#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <winsock2.h>
#include <windows.h>
#else
#include <sys/select.h>
#include <unistd.h>
#endif

#include "config.h"
#include "net.h"
#include "tls.h"

void net_sleep_ms(int milliseconds)
{
#ifdef _WIN32
    Sleep((DWORD)milliseconds);
#else
    usleep((useconds_t)milliseconds * 1000);
#endif
}

/* Chờ socket đọc được tối đa timeout_ms; trả 1 khi có dữ liệu, 0 khi hết giờ. */
static int wait_readable(int socket_fd, int timeout_ms)
{
    fd_set readable;
    struct timeval limit;
    FD_ZERO(&readable);
    FD_SET(socket_fd, &readable);
    limit.tv_sec = timeout_ms / 1000;
    limit.tv_usec = (timeout_ms % 1000) * 1000;
    return select(socket_fd + 1, &readable, NULL, NULL, &limit) > 0;
}

int net_request(const char *method, const char *host, int port, const char *path, const char *data, size_t length,
                int timeout_ms, http_response *out)
{
    tls_connection *connection = tls_connect(host, port, timeout_ms);
    char header[512];
    size_t received = 0;
    int status = 0;

    if (connection == NULL) {
        return 0;
    }
    snprintf(header, sizeof header,
             "%s %s HTTP/1.1\r\nHost: %s\r\nContent-Type: application/octet-stream\r\nContent-Length: %zu\r\n"
             "Connection: close\r\n\r\n",
             method, path, host, length);
    if (tls_write(connection, header, strlen(header)) < 0 || tls_write(connection, data, length) < 0) {
        tls_close(connection);
        return 0;
    }
    out->body = malloc(MAX_RESPONSE_BYTES);
    if (out->body == NULL) {
        tls_close(connection);
        return 0;
    }
    while (received < MAX_RESPONSE_BYTES) {
        int count;
        if (!wait_readable(tls_socket(connection), timeout_ms)) {
            status = 0; /* hết thời gian chờ: coi như lỗi mạng */
            break;
        }
        count = tls_read(connection, out->body + received, MAX_RESPONSE_BYTES - received);
        if (count <= 0) {
            break;
        }
        received += (size_t)count;
    }
    out->length = received;
    if (received > 12 && sscanf(out->body, "HTTP/1.%*d %d", &status) != 1) {
        status = 0;
    }
    tls_close(connection);
    return status;
}
