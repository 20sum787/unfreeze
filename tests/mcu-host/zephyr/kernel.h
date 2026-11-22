#pragma once
struct k_mutex {};
inline void k_mutex_init(k_mutex *) {}
constexpr int K_FOREVER = -1;
inline void k_mutex_lock(k_mutex *, int) {}
inline void k_mutex_unlock(k_mutex *) {}
#define K_THREAD_STACK_DEFINE(name, size) static unsigned char name[size]
#define K_THREAD_STACK_SIZEOF(name) sizeof(name)
struct k_thread {};
constexpr int K_NO_WAIT = 0;
inline void k_msleep(unsigned) {}
template<typename... T> inline void k_thread_create(T...) {}
