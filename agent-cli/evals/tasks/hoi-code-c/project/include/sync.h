#ifndef SAS_SYNC_H
#define SAS_SYNC_H

#include "http.h"

int sync_save(const char *path, const http_options *options);
int upload_save(const char *path, const http_options *options);

#endif
