#define _GNU_SOURCE
#include <stdio.h>
#include <stdint.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <stdlib.h>
#include <inttypes.h>
#include <string.h>
#include <errno.h>

/* For file-based approach - use regular file for shared memory
 * This works in environments where shm_open is not available
 */
#define SHARE_SIZE  1024              /* Only test 1 kB */
#define SHARE_FILE  "/tmp/simbricks_shm_test"  /* Temporary file for shared memory */

static inline void write_mem_fence(void) { __asm__ volatile("mfence" ::: "memory"); }
static inline void read_mem_fence(void)  { __asm__ volatile("mfence" ::: "memory"); }

int main(void)
{
    volatile uint64_t *share;
    int fd;
    
    printf("[shm_rw_syscall] Creating shared memory region using file-based approach...\n");
    
    /* Create and open the shared memory file */
    fd = open(SHARE_FILE, O_CREAT | O_RDWR, 0666);
    if (fd < 0) {
        perror("open failed");
        printf("[shm_rw_syscall] ERROR: Failed to create shared memory file\n");
        return 1;
    }
    
    /* Set the size of the shared memory file */
    if (ftruncate(fd, SHARE_SIZE) < 0) {
        perror("ftruncate failed");
        close(fd);
        unlink(SHARE_FILE);
        return 1;
    }
    
    /* Map shared memory into our address space */
    share = (volatile uint64_t *)mmap(
        NULL,                    /* Let kernel choose virtual address */
        SHARE_SIZE,              /* Size to map */
        PROT_READ | PROT_WRITE,  /* Read/write access */
        MAP_SHARED,              /* Shared mapping */
        fd,                      /* File descriptor for shared memory */
        0                        /* Offset */
    );
    
    if (share == MAP_FAILED) {
        perror("mmap failed");
        close(fd);
        unlink(SHARE_FILE);
        return 1;
    }
    
    printf("[shm_rw_syscall] Successfully mapped shared memory to virtual address %p\n", share);
    
    /* Initialize memory with pattern */
    printf("[shm_rw_syscall] Initializing memory with test pattern...\n");
    memset((void*)share, 0, SHARE_SIZE);
    
    /* 1. Write test pattern */
    printf("[shm_rw_syscall] Writing test pattern...\n");
    for (size_t i = 0; i < SHARE_SIZE / sizeof(uint64_t); ++i) {
        share[i] = 0xDEADBEEF00000000ULL | i;
    }
    write_mem_fence();
    
    /* 2. Read back and verify */
    printf("[shm_rw_syscall] Reading back and verifying...\n");
    int ok = 1;
    read_mem_fence();
    for (size_t i = 0; i < SHARE_SIZE / sizeof(uint64_t); ++i) {
        uint64_t v = share[i];
        if (v != (0xDEADBEEF00000000ULL | i)) {
            printf("[shm_rw_syscall] Mismatch at index %zu: expected 0x%016llX, got 0x%016llX\n", 
                   i, (unsigned long long)(0xDEADBEEF00000000ULL | i), (unsigned long long)v);
            ok = 0;
            break;
        }
    }
    
    /* 3. Print result */
    if (ok) {
        printf("[shm_rw_syscall] PASS: all %d bytes match\n", SHARE_SIZE);
    } else {
        printf("[shm_rw_syscall] FAIL: data mismatch\n");
    }
    
    /* Cleanup */
    munmap((void*)share, SHARE_SIZE);
    close(fd);
    unlink(SHARE_FILE);
    
    return ok ? 0 : 1;
}
