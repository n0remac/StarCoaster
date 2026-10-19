// Exercise the socket sequence used by OpenRCT2 in a real browser worker.
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>
#include <emscripten/emscripten.h>

static void* probe(void* unused) {
    (void)unused;
    int fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (fd < 0) { puts("FAIL socket"); return NULL; }
    fcntl(fd, F_SETFL, fcntl(fd, F_GETFL, 0) | O_NONBLOCK);
    struct sockaddr_in address = { .sin_family = AF_INET, .sin_port = htons(11753) };
    inet_pton(AF_INET, "127.0.0.1", &address.sin_addr);
    int result = connect(fd, (struct sockaddr*)&address, sizeof(address));
    if (result < 0 && errno != EINPROGRESS && errno != EWOULDBLOCK) {
        printf("FAIL connect errno=%d\n", errno); close(fd); return NULL;
    }
    int connected = 0;
    for (int i = 0; i < 50; i++) {
        int error = 0; socklen_t length = sizeof(error);
        fd_set writable; FD_ZERO(&writable); FD_SET(fd, &writable);
        struct timeval timeout = {0, 0};
        int ready = select(fd + 1, NULL, &writable, NULL, &timeout);
        if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &length) != 0) {
            puts("FAIL getsockopt"); close(fd); return NULL;
        }
        if (ready > 0 && FD_ISSET(fd, &writable) && error == 0) { connected = 1; break; }
        usleep(100000);
    }
    if (!connected) { puts("FAIL select timeout"); close(fd); return NULL; }
    if (send(fd, "PING", 4, 0) != 4) { puts("FAIL send"); close(fd); return NULL; }
    for (int i = 0; i < 50; i++) {
        char buffer[8];
        int count = recv(fd, buffer, sizeof(buffer), 0);
        if (count == 4 && memcmp(buffer, "PING", 4) == 0) {
            puts("PASS socket echo"); close(fd); return NULL;
        }
        if (count > 0 || (count < 0 && errno != EAGAIN && errno != EWOULDBLOCK)) {
            puts("FAIL recv"); close(fd); return NULL;
        }
        usleep(100000);
    }
    puts("FAIL recv timeout");
    close(fd);
    return NULL;
}

int main(void) {
    pthread_t thread;
    if (pthread_create(&thread, NULL, probe, NULL) != 0) {
        puts("FAIL thread"); return 1;
    }
    emscripten_exit_with_live_runtime();
    return 0;
}
