#ifndef SAS_NET_H
#define SAS_NET_H

#include <stddef.h>
#include "http.h"

/* Gửi một request qua TLS; trả mã HTTP, hoặc 0 khi lỗi mạng hay hết thời gian chờ. */
int net_request(const char *method, const char *host, int port, const char *path, const char *data, size_t length,
                int timeout_ms, http_response *out);
void net_sleep_ms(int milliseconds);

#endif
