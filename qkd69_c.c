// qkd69_c.c  —  最小動作のTLSクライアント（OpenSSL 3）
// 1) 127.0.0.1:8443 に TCP で接続
// 2) TLS を開始してメッセージを送信
// 3) サーバーからの応答を受信して表示

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>

// ▼ ネットワーク系で必須
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>

// ▼ OpenSSL
#include <openssl/ssl.h>
#include <openssl/err.h>

#define HOST "127.0.0.1"
#define PORT 8443

static void die(const char *where)
{
    fprintf(stderr, "ERROR at %s: %s\n", where, strerror(errno));
    exit(1);
}

int main(void)
{
    // --- OpenSSL 初期化 ---
    SSL_load_error_strings();
    OpenSSL_add_ssl_algorithms();

    SSL_CTX *ctx = SSL_CTX_new(TLS_client_method());
    if (!ctx) {
        ERR_print_errors_fp(stderr);
        return 1;
    }

    // 必要ならサーバ証明書検証を有効化（自己署名なら無効でもOK）
    // SSL_CTX_set_verify(ctx, SSL_VERIFY_PEER, NULL);
    // SSL_CTX_load_verify_locations(ctx, "server.crt", NULL);

    // --- ソケット作成 & 接続 ---
    int s = socket(AF_INET, SOCK_STREAM, 0);
    if (s < 0) die("socket");

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port   = htons(PORT);
    if (inet_pton(AF_INET, HOST, &addr.sin_addr) != 1) {
        fprintf(stderr, "inet_pton failed\n");
        close(s);
        return 1;
    }
    if (connect(s, (struct sockaddr *)&addr, sizeof(addr)) < 0) die("connect");

    // --- TLS ハンドシェイク ---
    SSL *ssl = SSL_new(ctx);
    if (!ssl) { ERR_print_errors_fp(stderr); close(s); SSL_CTX_free(ctx); return 1; }
    SSL_set_fd(ssl, s);
    // SNI（あれば）
    SSL_set_tlsext_host_name(ssl, HOST);

    if (SSL_connect(ssl) != 1) {
        fprintf(stderr, "SSL_connect failed\n");
        ERR_print_errors_fp(stderr);
        SSL_free(ssl);
        close(s);
        SSL_CTX_free(ctx);
        return 1;
    }
    printf("[C] TLS handshake ok\n");

    // --- 送信 ---
    const char *msg = "hello from client";
    if (SSL_write(ssl, msg, (int)strlen(msg)) <= 0) {
        fprintf(stderr, "SSL_write failed\n");
        ERR_print_errors_fp(stderr);
    }

    // --- 受信 ---
    unsigned char buf[2048];
    int r = SSL_read(ssl, buf, sizeof(buf)-1);
    if (r > 0) {
        buf[r] = '\0';
        printf("[C] recv: %s\n", buf);
    } else {
        fprintf(stderr, "SSL_read failed or closed\n");
        ERR_print_errors_fp(stderr);
    }

    // --- 後始末 ---
    SSL_shutdown(ssl);
    SSL_free(ssl);
    close(s);
    SSL_CTX_free(ctx);
    EVP_cleanup();

    return 0;
}

