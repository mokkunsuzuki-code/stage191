// qkd69_s.c  —  Stage69 TLS+QKDハイブリッド : サーバー（単体で完結版）
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <stdlib.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <sys/socket.h>

#include <openssl/ssl.h>
#include <openssl/err.h>
#include <openssl/evp.h>
#include <openssl/hmac.h>
#include <openssl/rand.h>
#include <openssl/kdf.h>     // HKDF

// ====== 可変部（必要なら変更）=========================================
#define HOST        "127.0.0.1"
#define PORT        8443
#define CERT_FILE   "server.crt"
#define KEY_FILE    "server.key"

// AES-GCM 用パラメータ
#define APP_KEY_LEN 32       // AES-256
#define APP_IV_LEN  12       // GCM 非推奨でない 96bit
#define TAG_LEN     16
// ====================================================================

// ---- AES-GCM 暗号化（out = ciphertext||tag）-------------------------
static int aead_encrypt(const unsigned char *key,
                        const unsigned char *aad, int aadlen,
                        const unsigned char *nonce, int noncelen,
                        const unsigned char *pt, int ptlen,
                        unsigned char *out, int *outlen)
{
    int len = 0, ctlen = 0;
    EVP_CIPHER_CTX *ctx = EVP_CIPHER_CTX_new();
    if(!ctx) return 0;

    if(!EVP_EncryptInit_ex(ctx, EVP_aes_256_gcm(), NULL, NULL, NULL)) goto err;
    if(!EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_IVLEN, noncelen, NULL)) goto err;
    if(!EVP_EncryptInit_ex(ctx, NULL, NULL, key, nonce)) goto err;

    if(aad && aadlen>0){
        if(!EVP_EncryptUpdate(ctx, NULL, &len, aad, aadlen)) goto err;
    }
    if(!EVP_EncryptUpdate(ctx, out, &len, pt, ptlen)) goto err;
    ctlen = len;

    if(!EVP_EncryptFinal_ex(ctx, out + ctlen, &len)) goto err;
    ctlen += len;

    if(!EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_GET_TAG, TAG_LEN, out + ctlen)) goto err;
    ctlen += TAG_LEN;

    *outlen = ctlen;
    EVP_CIPHER_CTX_free(ctx);
    return 1;
err:
    EVP_CIPHER_CTX_free(ctx);
    return 0;
}

// ---- QKD からアプリ鍵を導出（デモでは QKD = ランダム64B） ------------
//   tx = HKDF-SHA256(qkd, salt="", info="stage69 tx", len=32)
//   rx = HKDF-SHA256(qkd, salt="", info="stage69 rx", len=32)
static int derive_app_keys(const unsigned char *qkd, size_t qkd_len,
                           unsigned char *tx32, unsigned char *rx32)
{
    int ok = 0;
    EVP_PKEY_CTX *pctx = NULL;

    // tx
    pctx = EVP_PKEY_CTX_new_id(EVP_PKEY_HKDF, NULL);
    if(!pctx) goto done;
    if(EVP_PKEY_derive_init(pctx) <= 0) goto done;
    if(EVP_PKEY_CTX_set_hkdf_md(pctx, EVP_sha256()) <= 0) goto done;
    if(EVP_PKEY_CTX_set1_hkdf_salt(pctx, "", 0) <= 0) goto done;
    if(EVP_PKEY_CTX_set1_hkdf_key(pctx, qkd, (int)qkd_len) <= 0) goto done;
    if(EVP_PKEY_CTX_add1_hkdf_info(pctx, "stage69 tx", 10) <= 0) goto done;
    size_t len = APP_KEY_LEN;
    if(EVP_PKEY_derive(pctx, tx32, &len) <= 0 || len != APP_KEY_LEN) goto done;
    EVP_PKEY_CTX_free(pctx); pctx = NULL;

    // rx
    pctx = EVP_PKEY_CTX_new_id(EVP_PKEY_HKDF, NULL);
    if(!pctx) goto done;
    if(EVP_PKEY_derive_init(pctx) <= 0) goto done;
    if(EVP_PKEY_CTX_set_hkdf_md(pctx, EVP_sha256()) <= 0) goto done;
    if(EVP_PKEY_CTX_set1_hkdf_salt(pctx, "", 0) <= 0) goto done;
    if(EVP_PKEY_CTX_set1_hkdf_key(pctx, qkd, (int)qkd_len) <= 0) goto done;
    if(EVP_PKEY_CTX_add1_hkdf_info(pctx, "stage69 rx", 10) <= 0) goto done;
    len = APP_KEY_LEN;
    if(EVP_PKEY_derive(pctx, rx32, &len) <= 0 || len != APP_KEY_LEN) goto done;

    ok = 1;
done:
    if(pctx) EVP_PKEY_CTX_free(pctx);
    return ok;
}

static void openssl_fatal(const char *where)
{
    fprintf(stderr, "[OpenSSL] %s failed\n", where);
    ERR_print_errors_fp(stderr);
}

// ---- メイン（TLSサーバー → 接続1件受けて暗号メッセージ送信） ---------
int main(void)
{
    // OpenSSL 初期化
    SSL_load_error_strings();
    OpenSSL_add_ssl_algorithms();

    SSL_CTX *ctx = SSL_CTX_new(TLS_server_method());
    if(!ctx){ openssl_fatal("SSL_CTX_new"); return 1; }

    if(SSL_CTX_use_certificate_file(ctx, CERT_FILE, SSL_FILETYPE_PEM) != 1){
        openssl_fatal("use_certificate"); return 1;
    }
    if(SSL_CTX_use_PrivateKey_file(ctx, KEY_FILE, SSL_FILETYPE_PEM) != 1){
        openssl_fatal("use_privatekey"); return 1;
    }
    if(SSL_CTX_check_private_key(ctx) != 1){
        openssl_fatal("check_private_key"); return 1;
    }

    // ソケット待ち受け
    int ls = socket(AF_INET, SOCK_STREAM, 0);
    if(ls < 0){ perror("socket"); return 1; }

    int on = 1;
    setsockopt(ls, SOL_SOCKET, SO_REUSEADDR, &on, sizeof(on));

    struct sockaddr_in addr = {0};
    addr.sin_family = AF_INET;
    addr.sin_port   = htons(PORT);
    inet_pton(AF_INET, HOST, &addr.sin_addr);

    if(bind(ls, (struct sockaddr*)&addr, sizeof(addr)) < 0){ perror("bind"); return 1; }
    if(listen(ls, 1) < 0){ perror("listen"); return 1; }

    printf("[S] TLS server on https://%s:%d\n", HOST, PORT);

    for(;;) {
        struct sockaddr_in cli; socklen_t clilen = sizeof(cli);
        int cs = accept(ls, (struct sockaddr*)&cli, &clilen);
        if(cs < 0){ perror("accept"); continue; }

        SSL *ssl = SSL_new(ctx);
        SSL_set_fd(ssl, cs);

        if(SSL_accept(ssl) != 1){
            openssl_fatal("SSL_accept");
            SSL_free(ssl); close(cs); continue;
        }
        printf("[S] TLS handshake ok\n");

        // --- デモ用: QKD(将来の共有鍵) をランダム64Bで代用 ---
        unsigned char qkd[64];
        RAND_bytes(qkd, sizeof(qkd));

        unsigned char k_tx[APP_KEY_LEN], k_rx[APP_KEY_LEN];
        if(!derive_app_keys(qkd, sizeof(qkd), k_tx, k_rx)){
            fprintf(stderr, "derive_app_keys failed\n");
            SSL_shutdown(ssl); SSL_free(ssl); close(cs); continue;
        }

        // 送るメッセージを AES-GCM で暗号化し、TLSの上に「nonce||ct」を送る
        const unsigned char aad[] = "Stage69-AAD";
        const unsigned char msg[] =
            "Hello from Stage69 server with TLS+QKD hybrid";
        unsigned char iv[APP_IV_LEN];
        RAND_bytes(iv, sizeof(iv));

        unsigned char ct[sizeof(msg) + TAG_LEN + 16]; // 余裕を持たせる
        int ctlen = 0;
        if(!aead_encrypt(k_tx, aad, (int)sizeof(aad)-1,
                         iv, sizeof(iv), msg, (int)sizeof(msg)-1,
                         ct, &ctlen))
        {
            fprintf(stderr, "aead_encrypt failed\n");
            SSL_shutdown(ssl); SSL_free(ssl); close(cs); continue;
        }

        unsigned char buf[APP_IV_LEN + 1024];
        memcpy(buf, iv, APP_IV_LEN);
        memcpy(buf + APP_IV_LEN, ct, ctlen);
        int outlen = APP_IV_LEN + ctlen;

        int n = SSL_write(ssl, buf, outlen);
        printf("[S] sent %d bytes (iv %d + ct %d)\n", n, APP_IV_LEN, ctlen);

        SSL_shutdown(ssl);
        SSL_free(ssl);
        close(cs);
        // 1件送ったら終了（必要なら while を継続に）
        break;
    }

    close(ls);
    SSL_CTX_free(ctx);
    EVP_cleanup();
    return 0;
}
