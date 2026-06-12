/* XCurl.dll CA-injecting shim.
 * The game's libHttpClient CurlProvider never sets CURLOPT_CAINFO, and this
 * OpenSSL libcurl ignores CURL_CA_BUNDLE/SSL_CERT_FILE env (its compiled default
 * CAINFO overrides OpenSSL's env paths) and has no Windows app-dir auto-search.
 * So TLS verify (enforced in-game) fails. This shim exports the 16 curl_* symbols
 * the game resolves, forwards them to the REAL libcurl (shipped as xcurl_real.dll
 * beside this DLL), and intercepts curl_easy_init to set CURLOPT_CAINFO to
 * "cacert.pem" sitting next to this DLL — fully self-contained. */
#include <windows.h>
#include <string.h>
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>

typedef void CURL; typedef void CURLM;
#define CURLOPT_CAINFO 10065
#define CURLOPT_URL    10002
#define CURLINFO_RESPONSE_CODE 0x200002
#define CURLINFO_EFFECTIVE_URL 0x100001

static CRITICAL_SECTION g_cs;
static int  g_cs_ready = 0;
static HMODULE g_real = NULL;
static char g_ca[1024];
static char g_logpath[1024];
static int  g_log = 0;          /* enabled when XCURL_LOG=1 in the env */

static void xlog(const char* fmt, ...){
    if (!g_log || !g_logpath[0]) return;
    FILE* f = fopen(g_logpath, "a");
    if (!f) return;
    va_list ap; va_start(ap, fmt); vfprintf(f, fmt, ap); va_end(ap);
    fclose(f);
}

static CURL* (*r_easy_init)(void);
static void  (*r_easy_cleanup)(CURL*);
static int   (*r_easy_setopt)(CURL*, int, void*);
static int   (*r_easy_getinfo)(CURL*, int, void*);
static const char* (*r_easy_strerror)(int);
static int   (*r_global_init)(long);
static void  (*r_global_cleanup)(void);
static CURLM*(*r_multi_init)(void);
static int   (*r_multi_cleanup)(CURLM*);
static int   (*r_multi_add)(CURLM*, CURL*);
static int   (*r_multi_remove)(CURLM*, CURL*);
static int   (*r_multi_perform)(CURLM*, int*);
static int   (*r_multi_poll)(CURLM*, void*, unsigned, int, int*);
static int   (*r_multi_wait)(CURLM*, void*, unsigned, int, int*);
static void* (*r_multi_info_read)(CURLM*, int*);
static void* (*r_slist_append)(void*, const char*);
static void  (*r_slist_free_all)(void*);

static void init_once(void){
    if (g_real) return;
    if (!g_cs_ready) return;            /* DllMain not run yet (shouldn't happen) */
    EnterCriticalSection(&g_cs);
    if (!g_real){
        char dir[1024]; HMODULE self=NULL;
        /* FROM_ADDRESS|UNCHANGED_REFCOUNT — resolve this DLL's own path */
        GetModuleHandleExA(0x4|0x2,(LPCSTR)&init_once,&self);
        dir[0]=0;
        if (self) GetModuleFileNameA(self, dir, sizeof dir);
        char* s=strrchr(dir,'\\');
        if (s){
            size_t n=(size_t)(s-dir)+1;
            memcpy(g_ca,dir,n); strcpy(g_ca+n,"cacert.pem");
            memcpy(g_logpath,dir,n); strcpy(g_logpath+n,"xcurl.log");
            char rp[1024]; memcpy(rp,dir,n); strcpy(rp+n,"xcurl_real.dll");
            g_real=LoadLibraryA(rp);
        }
        if (!g_real) { g_ca[0]=0; strcpy(g_ca,"cacert.pem"); g_real=LoadLibraryA("xcurl_real.dll"); }
        { char v[8]={0}; if (GetEnvironmentVariableA("XCURL_LOG",v,sizeof v) && v[0]=='1') g_log=1; }
        xlog("=== xcurl shim init: real=%p ca=%s ===\n", (void*)g_real, g_ca);
        if (g_real){
            HMODULE r=g_real;
            r_easy_init      =(void*)GetProcAddress(r,"curl_easy_init");
            r_easy_cleanup   =(void*)GetProcAddress(r,"curl_easy_cleanup");
            r_easy_setopt    =(void*)GetProcAddress(r,"curl_easy_setopt");
            r_easy_getinfo   =(void*)GetProcAddress(r,"curl_easy_getinfo");
            r_easy_strerror  =(void*)GetProcAddress(r,"curl_easy_strerror");
            r_global_init    =(void*)GetProcAddress(r,"curl_global_init");
            r_global_cleanup =(void*)GetProcAddress(r,"curl_global_cleanup");
            r_multi_init     =(void*)GetProcAddress(r,"curl_multi_init");
            r_multi_cleanup  =(void*)GetProcAddress(r,"curl_multi_cleanup");
            r_multi_add      =(void*)GetProcAddress(r,"curl_multi_add_handle");
            r_multi_remove   =(void*)GetProcAddress(r,"curl_multi_remove_handle");
            r_multi_perform  =(void*)GetProcAddress(r,"curl_multi_perform");
            r_multi_poll     =(void*)GetProcAddress(r,"curl_multi_poll");
            r_multi_wait     =(void*)GetProcAddress(r,"curl_multi_wait");
            r_multi_info_read=(void*)GetProcAddress(r,"curl_multi_info_read");
            r_slist_append   =(void*)GetProcAddress(r,"curl_slist_append");
            r_slist_free_all =(void*)GetProcAddress(r,"curl_slist_free_all");
        }
    }
    LeaveCriticalSection(&g_cs);
}

/* tiny handle->URL map so we can label perform/info-read results */
#define XMAP_N 256
static CURL* g_h[XMAP_N];
static char  g_u[XMAP_N][256];
static void xmap_set(CURL* h, const char* url){
    int i, free_i=-1;
    if(!g_cs_ready) return;
    EnterCriticalSection(&g_cs);
    for(i=0;i<XMAP_N;i++){ if(g_h[i]==h){free_i=i;break;} if(free_i<0&&!g_h[i])free_i=i; }
    if(free_i>=0){ g_h[free_i]=h; if(url){ strncpy(g_u[free_i],url,255); g_u[free_i][255]=0; } else g_u[free_i][0]=0; }
    LeaveCriticalSection(&g_cs);
}
static const char* xmap_get(CURL* h){
    int i; for(i=0;i<XMAP_N;i++) if(g_h[i]==h) return g_u[i];
    return "?";
}
static void xmap_del(CURL* h){
    int i; if(!g_cs_ready) return;
    EnterCriticalSection(&g_cs);
    for(i=0;i<XMAP_N;i++) if(g_h[i]==h){ g_h[i]=0; g_u[i][0]=0; break; }
    LeaveCriticalSection(&g_cs);
}

__declspec(dllexport) CURL* curl_easy_init(void){
    init_once();
    if(!r_easy_init) return NULL;
    CURL* h=r_easy_init();
    if(h && r_easy_setopt && g_ca[0]) r_easy_setopt(h, CURLOPT_CAINFO, g_ca);
    return h;
}
__declspec(dllexport) void curl_easy_cleanup(CURL* h){ init_once(); xmap_del(h); if(r_easy_cleanup) r_easy_cleanup(h); }
__declspec(dllexport) int  curl_easy_setopt(CURL* h,int o,void* v){
    init_once();
    if(o==CURLOPT_URL && v){
        const char* url=(const char*)v;
        /* Minecraft builds Xbox People Hub URLs with an empty owner —
         * /users/xuid()/people/... — which peoplehub rejects with HTTP 400
         * "Owner XUID is required", leaving the in-game Friends list/search
         * empty. The caller is implied by the XBL token, so rewrite the empty
         * owner to "me" (verified: peoplehub returns 200 for /users/me/...).
         * The rewritten URL must outlive this call: this libcurl keeps the
         * CURLOPT_URL pointer (a stack/transient copy dangles and faults in
         * perform). Allocate it and leak it — tiny and only on Friends calls. */
        const char* bad=strstr(url,"/users/xuid()/");
        if(bad){
            size_t pre=(size_t)(bad-url);
            const char* rest=bad+14;              /* strlen("/users/xuid()/") */
            size_t need=pre+10+strlen(rest)+1;    /* 10 = strlen("/users/me/") */
            char* fixed=(char*)malloc(need);
            if(fixed){
                memcpy(fixed,url,pre);
                memcpy(fixed+pre,"/users/me/",10);
                strcpy(fixed+pre+10,rest);
                if(g_log) xmap_set(h,fixed);
                xlog("rewrote empty xuid() -> me: %s\n", fixed);
                return r_easy_setopt?r_easy_setopt(h,o,(void*)fixed):-1;
            }
        }
        if(g_log) xmap_set(h,url);
    }
    return r_easy_setopt?r_easy_setopt(h,o,v):-1;
}
__declspec(dllexport) int  curl_easy_getinfo(CURL* h,int o,void* v){ init_once(); return r_easy_getinfo?r_easy_getinfo(h,o,v):-1; }
__declspec(dllexport) const char* curl_easy_strerror(int c){ init_once(); return r_easy_strerror?r_easy_strerror(c):""; }
__declspec(dllexport) int  curl_global_init(long f){ init_once(); return r_global_init?r_global_init(f):-1; }
__declspec(dllexport) void curl_global_cleanup(void){ init_once(); if(r_global_cleanup) r_global_cleanup(); }
__declspec(dllexport) CURLM* curl_multi_init(void){ init_once(); return r_multi_init?r_multi_init():NULL; }
__declspec(dllexport) int  curl_multi_cleanup(CURLM* m){ init_once(); return r_multi_cleanup?r_multi_cleanup(m):-1; }
__declspec(dllexport) int  curl_multi_add_handle(CURLM* m,CURL* h){ init_once(); return r_multi_add?r_multi_add(m,h):-1; }
__declspec(dllexport) int  curl_multi_remove_handle(CURLM* m,CURL* h){ init_once(); return r_multi_remove?r_multi_remove(m,h):-1; }
__declspec(dllexport) int  curl_multi_perform(CURLM* m,int* n){ init_once(); return r_multi_perform?r_multi_perform(m,n):-1; }
__declspec(dllexport) int  curl_multi_poll(CURLM* m,void* e,unsigned ne,int t,int* nr){ init_once(); return r_multi_poll?r_multi_poll(m,e,ne,t,nr):-1; }
__declspec(dllexport) int  curl_multi_wait(CURLM* m,void* e,unsigned ne,int t,int* nr){ init_once(); return r_multi_wait?r_multi_wait(m,e,ne,t,nr):-1; }
__declspec(dllexport) void* curl_multi_info_read(CURLM* m,int* q){
    init_once();
    void* msg = r_multi_info_read ? r_multi_info_read(m,q) : NULL;
    /* CURLMsg { int msg; CURL* easy_handle; union { void* whatever; int result; } data; } */
    if(g_log && msg){
        struct { int msg; CURL* e; void* res; } *mm = msg;
        if(mm->msg==1 /*CURLMSG_DONE*/ && mm->e){
            long code=0; if(r_easy_getinfo) r_easy_getinfo(mm->e,CURLINFO_RESPONSE_CODE,&code);
            int rc=(int)(LONG_PTR)mm->res;
            xlog("DONE rc=%d http=%ld url=%s\n", rc, code, xmap_get(mm->e));
        }
    }
    return msg;
}
__declspec(dllexport) void* curl_slist_append(void* l,const char* s){ init_once(); return r_slist_append?r_slist_append(l,s):NULL; }
__declspec(dllexport) void curl_slist_free_all(void* l){ init_once(); if(r_slist_free_all) r_slist_free_all(l); }

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID v){
    (void)h;(void)v;
    if(reason==DLL_PROCESS_ATTACH){ InitializeCriticalSection(&g_cs); g_cs_ready=1; }
    return TRUE;
}
