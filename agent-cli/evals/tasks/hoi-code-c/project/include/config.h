#ifndef SAS_CONFIG_H
#define SAS_CONFIG_H

/* Máy chủ bảng xếp hạng */
#define SERVER_HOST "rank.sas-game.example"
#define SERVER_PORT 443

/* Mặc định cho mọi request; từng lệnh có thể đặt lại (xem main.c) */
#define DEFAULT_TIMEOUT_MS 10000
#define RETRY_LIMIT 3
#define RETRY_BASE_DELAY_MS 500

/* Kích thước tối đa của phản hồi máy chủ */
#define MAX_RESPONSE_BYTES (256 * 1024)

#endif
