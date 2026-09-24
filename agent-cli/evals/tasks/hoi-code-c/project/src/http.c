#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "config.h"
#include "http.h"
#include "net.h"

http_options http_default_options(void)
{
    http_options options;
    options.timeout_ms = DEFAULT_TIMEOUT_MS;
    options.retries = RETRY_LIMIT;
    return options;
}

static int should_retry(int status)
{
    /* Lỗi mạng (status 0) hoặc lỗi máy chủ 5xx: thử lại được.
       4xx là request sai, gửi lại y nguyên cũng vậy nên không thử lại. */
    return status == 0 || status >= 500;
}

int http_post(const char *path, const char *data, size_t length, const http_options *options, http_response *out)
{
    int attempt;
    int status = 0;

    for (attempt = 0; attempt <= options->retries; attempt++) {
        if (attempt > 0) {
            int delay = RETRY_BASE_DELAY_MS << (attempt - 1); /* 500, 1000, 2000 ms */
            fprintf(stderr, "Thử lại lần %d sau %d ms\n", attempt, delay);
            net_sleep_ms(delay);
            http_response_free(out);
        }
        status = net_request("POST", SERVER_HOST, SERVER_PORT, path, data, length, options->timeout_ms, out);
        if (!should_retry(status)) {
            return status;
        }
    }
    return status;
}

void http_response_free(http_response *response)
{
    free(response->body);
    response->body = NULL;
    response->length = 0;
}
