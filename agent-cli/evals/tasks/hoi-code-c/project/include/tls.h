#ifndef SAS_TLS_H
#define SAS_TLS_H

#include <stddef.h>

/* Lớp mỏng quanh thư viện TLS của hệ điều hành (Schannel trên Windows, OpenSSL nơi khác). */
typedef struct tls_connection tls_connection;

tls_connection *tls_connect(const char *host, int port, int timeout_ms);
int tls_write(tls_connection *connection, const void *data, size_t length);
int tls_read(tls_connection *connection, void *buffer, size_t capacity);
int tls_socket(tls_connection *connection);
void tls_close(tls_connection *connection);

#endif
