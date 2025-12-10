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

/* Simple application to read/write fixed physical address 0x3FC0000
 * No command line parameters - just runs a simple test
 */
#define FIXED_PHYS_ADDR 0x80000000UL    /* Fixed physical address to access - moved to 2GB to avoid overlap with main memory */
#define MAP_SIZE        4096           /* 4KB mapping size */
#define TEST_VALUE      0xDEADBEEFCAFEBABEULL  /* Test value to write */

static inline void write_mem_fence(void) { __asm__ volatile("mfence" ::: "memory"); }
static inline void read_mem_fence(void)  { __asm__ volatile("mfence" ::: "memory"); }

int main(void) {
    volatile uint64_t *mem_ptr;
    int fd;
    
    printf("[shm_rw_fixed_addr] Accessing fixed physical address 0x%lX\n", FIXED_PHYS_ADDR);
    printf("[shm_rw_fixed_addr] Note: Address moved to 0x80000000 (2GB) to avoid overlap with main memory\n");
    
    /* Try /dev/mem first for direct physical memory access */
    fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) {
        printf("[shm_rw_fixed_addr] /dev/mem not available (%s), using file-based approach\n", strerror(errno));
        fd = -1; /* Mark as invalid */
    } else {
        printf("[shm_rw_fixed_addr] /dev/mem opened successfully, attempting direct mapping\n");
        
        /* Map physical memory directly - use page-aligned address */
        uintptr_t aligned_addr = FIXED_PHYS_ADDR & ~(sysconf(_SC_PAGE_SIZE) - 1);
        size_t offset = FIXED_PHYS_ADDR - aligned_addr;
        
        mem_ptr = (volatile uint64_t *)mmap(
            NULL,                    /* Let kernel choose virtual address */
            MAP_SIZE + offset,       /* Size to map (include offset) */
            PROT_READ | PROT_WRITE,  /* Read/write access */
            MAP_SHARED,              /* Shared mapping */
            fd,                      /* File descriptor for /dev/mem */
            aligned_addr             /* Aligned physical address to map */
        );
        
        if (mem_ptr == MAP_FAILED) {
            printf("[shm_rw_fixed_addr] /dev/mem mmap failed: %s, falling back to file-based approach\n", strerror(errno));
            close(fd);
            fd = -1; /* Mark as invalid, will use fallback */
        } else {
            printf("[shm_rw_fixed_addr] Successfully mapped /dev/mem at aligned address 0x%lX\n", aligned_addr);
            /* Adjust pointer to point to the exact physical address */
            mem_ptr = (volatile uint64_t *)((uint8_t *)mem_ptr + offset);
        }
    }
    
    /* Fallback to file-based approach if /dev/mem failed */
    if (fd < 0) {
        printf("[shm_rw_fixed_addr] Using file-based approach\n");
        
        /* Create a temporary file and map it */
        fd = open("/tmp/fixed_addr_mem", O_CREAT | O_RDWR, 0666);
        if (fd < 0) {
            perror("Failed to create temporary file");
            return 1;
        }
        
        /* Make file large enough to simulate the physical address space */
        if (ftruncate(fd, FIXED_PHYS_ADDR + MAP_SIZE) < 0) {
            perror("ftruncate failed");
            close(fd);
            unlink("/tmp/fixed_addr_mem");
            return 1;
        }
        
        /* Map the file at the specific offset */
        mem_ptr = (volatile uint64_t *)mmap(
            NULL,                    /* Let kernel choose virtual address */
            MAP_SIZE,                /* Size to map */
            PROT_READ | PROT_WRITE,  /* Read/write access */
            MAP_SHARED,              /* Shared mapping */
            fd,                      /* File descriptor */
            FIXED_PHYS_ADDR          /* Offset in file (simulates physical address) */
        );
    }
    
    if (mem_ptr == MAP_FAILED) {
        perror("mmap failed");
        close(fd);
        if (fd >= 0 && access("/tmp/fixed_addr_mem", F_OK) == 0) {
            unlink("/tmp/fixed_addr_mem");
        }
        return 1;
    }
    
    printf("[shm_rw_fixed_addr] Successfully mapped address 0x%lX to virtual address %p\n", 
           FIXED_PHYS_ADDR, mem_ptr);
    
    /* Simple test: write and read back */
    printf("[shm_rw_fixed_addr] Running simple test...\n");
    
    /* Read current value */
    read_mem_fence();
    uint64_t original_value = mem_ptr[0];
    printf("[shm_rw_fixed_addr] Original value at 0x%lX: 0x%016llX\n", 
           FIXED_PHYS_ADDR, (unsigned long long)original_value);
    
    /* Write test value */
    printf("[shm_rw_fixed_addr] Writing test value 0x%016llX\n", (unsigned long long)TEST_VALUE);
    write_mem_fence();
    mem_ptr[0] = TEST_VALUE;
    write_mem_fence();
    
    /* Read back and verify */
    read_mem_fence();
    uint64_t read_value = mem_ptr[0];
    printf("[shm_rw_fixed_addr] Read back value: 0x%016llX\n", (unsigned long long)read_value);
    
    if (read_value == TEST_VALUE) {
        printf("[shm_rw_fixed_addr] PASS: Read back matches written value\n");
    } else {
        printf("[shm_rw_fixed_addr] FAIL: Read back does not match written value\n");
    }
    
    /* Test multiple locations in the mapped region */
    printf("[shm_rw_fixed_addr] Testing multiple memory locations...\n");
    int test_passed = 1;
    for (int i = 0; i < 4; i++) {
        uint64_t test_val = 0xDEADBEEF00000000ULL | i;
        mem_ptr[i] = test_val;
        write_mem_fence();
        
        read_mem_fence();
        uint64_t read_val = mem_ptr[i];
        
        printf("[shm_rw_fixed_addr] Location [%d]: wrote 0x%016llX, read 0x%016llX\n", 
               i, (unsigned long long)test_val, (unsigned long long)read_val);
        
        if (read_val != test_val) {
            printf("[shm_rw_fixed_addr] FAIL at offset %d: mismatch detected\n", i);
            test_passed = 0;
        }
    }
    
    if (test_passed) {
        printf("[shm_rw_fixed_addr] PASS: All test locations match\n");
    } else {
        printf("[shm_rw_fixed_addr] FAIL: Some locations had mismatches\n");
    }
    
    /* Restore original value (optional) */
    printf("[shm_rw_fixed_addr] Restoring original value\n");
    write_mem_fence();
    mem_ptr[0] = original_value;
    write_mem_fence();
    
    /* Cleanup */
    munmap((void*)mem_ptr, MAP_SIZE);
    close(fd);
    if (access("/tmp/fixed_addr_mem", F_OK) == 0) {
        unlink("/tmp/fixed_addr_mem");
    }
    
    printf("[shm_rw_fixed_addr] Test completed successfully\n");
    return test_passed ? 0 : 1;
}
