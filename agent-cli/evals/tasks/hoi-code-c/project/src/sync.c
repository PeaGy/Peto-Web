#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "http.h"
#include "sync.h"

static char *read_file(const char *path, size_t *length)
{
    FILE *file = fopen(path, "rb");
    char *data;
    long size;

    if (file == NULL) {
        return NULL;
    }
    fseek(file, 0, SEEK_END);
    size = ftell(file);
    fseek(file, 0, SEEK_SET);
    data = malloc((size_t)size);
    if (data != NULL && fread(data, 1, (size_t)size, file) != (size_t)size) {
        free(data);
        data = NULL;
    }
    fclose(file);
    *length = (size_t)size;
    return data;
}

static int send_save(const char *path, const char *endpoint, const http_options *options, int show_rank)
{
    size_t length = 0;
    char *data = read_file(path, &length);
    http_response response = {0, NULL, 0};
    int status;

    if (data == NULL) {
        fprintf(stderr, "Không đọc được %s\n", path);
        return 1;
    }
    status = http_post(endpoint, data, length, options, &response);
    free(data);
    if (status != 200) {
        fprintf(stderr, status ? "Máy chủ trả lỗi %d\n" : "Không kết nối được máy chủ\n", status);
        http_response_free(&response);
        return 1;
    }
    if (show_rank) {
        const char *rank = strstr(response.body, "\"rank\":");
        printf("Hạng hiện tại: %s\n", rank ? rank + 7 : "(không rõ)");
    }
    http_response_free(&response);
    return 0;
}

int sync_save(const char *path, const http_options *options)
{
    return send_save(path, "/api/v2/sync", options, 1);
}

int upload_save(const char *path, const http_options *options)
{
    return send_save(path, "/api/v2/upload", options, 0);
}
