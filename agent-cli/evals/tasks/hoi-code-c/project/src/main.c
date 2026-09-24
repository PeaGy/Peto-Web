#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "http.h"
#include "sync.h"

static void usage(void)
{
    fprintf(stderr, "Dùng: sas-net sync <file.sav>\n     sas-net upload <file.sav> [--timeout giây]\n");
}

int main(int argc, char **argv)
{
    http_options options = http_default_options();

    if (argc < 3) {
        usage();
        return 2;
    }
    if (strcmp(argv[1], "sync") == 0) {
        /* Máy chủ xử lý sync chậm (so cả lịch sử điểm), nên chờ lâu hơn mặc định. */
        options.timeout_ms = 15 * 1000;
        return sync_save(argv[2], &options);
    }
    if (strcmp(argv[1], "upload") == 0) {
        if (argc >= 5 && strcmp(argv[3], "--timeout") == 0) {
            options.timeout_ms = atoi(argv[4]) * 1000;
        }
        return upload_save(argv[2], &options);
    }
    usage();
    return 2;
}
