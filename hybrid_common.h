\
#ifndef HYBRID_COMMON_H
#define HYBRID_COMMON_H

// Stage69 common helper (ASCII only)
// AES-GCM helpers using OpenSSL EVP. Tag is appended to the end of ciphertext.

#include <openssl/evp.h>
#include <string.h>

#define APP_IV_LEN 12
#define APP_TAG_LEN 16

// AEAD encrypt: out_ct = ciphertext || tag(16)
// returns 1 on success, 0 on failure.
static int aead_encrypt(const unsigned char* key,
                        const unsigned char* aad, int aadlen,
                        const unsigned char* nonce12,
                        const unsigned char* pt, int ptlen,
                        unsigned char* out_ct, int* outlen) {
    int len = 0, c_len = 0;
    EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
    if (!ctx) return 0;

    if (EVP_EncryptInit_ex(ctx, EVP_aes_256_gcm(), NULL, NULL, NULL) != 1) { EVP_CIPHER_CTX_free(ctx); return 0; }
    if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_IVLEN, APP_IV_LEN, NULL) != 1) { EVP_CIPHER_CTX_free(ctx); return 0; }
    if (EVP_EncryptInit_ex(ctx, NULL, NULL, key, nonce12) != 1) { EVP_CIPHER_CTX_free(ctx); return 0; }

    if (aad && aadlen > 0) {
        if (EVP_EncryptUpdate(ctx, NULL, &len, aad, aadlen) != 1) { EVP_CIPHER_CTX_free(ctx); return 0; }
    }
    if (EVP_EncryptUpdate(ctx, out_ct, &len, pt, ptlen) != 1) { EVP_CIPHER_CTX_free(ctx); return 0; }
    c_len = len;

    if (EVP_EncryptFinal_ex(ctx, out_ct + c_len, &len) != 1) { EVP_CIPHER_CTX_free(ctx); return 0; }
    c_len += len;

    if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_GET_TAG, APP_TAG_LEN, out_ct + c_len) != 1) { EVP_CIPHER_CTX_free(ctx); return 0; }
    c_len += APP_TAG_LEN;

    EVP_CIPHER_CTX_free(ctx);
    if (outlen) *outlen = c_len;
    return 1;
}

// AEAD decrypt: input ct includes tag at tail (last 16 bytes).
// out_pt receives plaintext. returns 1 on success, 0 on failure.
static int aead_decrypt(const unsigned char* key,
                        const unsigned char* aad, int aadlen,
                        const unsigned char* nonce12,
                        const unsigned char* ct, int ctlen,
                        unsigned char* out_pt, int* outlen) {
    if (ctlen < APP_TAG_LEN) return 0;

    int ptlen = 0, len = 0;
    const unsigned char* tag = ct + (ctlen - APP_TAG_LEN);
    int clen_wo_tag = ctlen - APP_TAG_LEN;

    EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
    if (!ctx) return 0;

    if (EVP_DecryptInit_ex(ctx, EVP_aes_256_gcm(), NULL, NULL, NULL) != 1) { EVP_CIPHER_CTX_free(ctx); return 0; }
    if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_IVLEN, APP_IV_LEN, NULL) != 1) { EVP_CIPHER_CTX_free(ctx); return 0; }
    if (EVP_DecryptInit_ex(ctx, NULL, NULL, key, nonce12) != 1) { EVP_CIPHER_CTX_free(ctx); return 0; }

    if (aad && aadlen > 0) {
        if (EVP_DecryptUpdate(ctx, NULL, &len, aad, aadlen) != 1) { EVP_CIPHER_CTX_free(ctx); return 0; }
    }
    if (EVP_DecryptUpdate(ctx, out_pt, &len, ct, clen_wo_tag) != 1) { EVP_CIPHER_CTX_free(ctx); return 0; }
    ptlen = len;

    if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_TAG, APP_TAG_LEN, (void*)tag) != 1) { EVP_CIPHER_CTX_free(ctx); return 0; }

    // Returns 1 only if tag is valid.
    int ok = EVP_DecryptFinal_ex(ctx, out_pt + ptlen, &len);
    EVP_CIPHER_CTX_free(ctx);
    if (ok <= 0) return 0;

    ptlen += len;
    if (outlen) *outlen = ptlen;
    return 1;
}

#endif // HYBRID_COMMON_H
