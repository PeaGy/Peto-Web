#ifndef SAS_HTTP_H
#define SAS_HTTP_H

#include <stddef.h>

typedef struct {
    int timeout_ms; /* hết thời gian này thì bỏ request */
    int retries;    /* số lần thử lại khi lỗi mạng hay lỗi 5xx */
} http_options;

typedef struct {
    int status;
    char *body;
    size_t length;
} http_response;

http_options http_default_options(void);
int http_post(const char *path, const char *data, size_t length, const http_options *options, http_response *out);
void http_response_free(http_response *response);

#endif
