/* Candidate Linux x86-64 seccomp preload; NOT an isolation proof.
 *
 * Load as an ELF shared object before the Agent JS begins. Deny new programs,
 * separate processes, namespace changes and ptrace; permit thread creation
 * through clone only when CLONE_THREAD and CLONE_VM are both set. clone3 is
 * reported unavailable so runtimes can fall back to clone. A separate network
 * namespace, trusted runtime, tool policy and negative verification remain
 * mandatory. This file is not compiled or activated by this repository.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/sched.h>
#include <linux/seccomp.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <unistd.h>

#if !defined(__linux__) || !defined(__x86_64__)
#error "candidate filter supports Linux x86-64 only"
#endif

#define DENY_SYSCALL(nr) \
    BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (nr), 0, 1), \
    BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM)

__attribute__((constructor)) static void install_filter(void) {
    struct sock_filter filter[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, arch)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AUDIT_ARCH_X86_64, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
        BPF_JUMP(BPF_JMP | BPF_JGE | BPF_K, 0x40000000U, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        DENY_SYSCALL(__NR_execve),
        DENY_SYSCALL(__NR_execveat),
        DENY_SYSCALL(__NR_fork),
        DENY_SYSCALL(__NR_vfork),
        DENY_SYSCALL(__NR_ptrace),
        DENY_SYSCALL(__NR_unshare),
        DENY_SYSCALL(__NR_setns),
        DENY_SYSCALL(__NR_mount),
        DENY_SYSCALL(__NR_umount2),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_clone3, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | ENOSYS),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_clone, 0, 5),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, args[0])),
        BPF_STMT(BPF_ALU | BPF_AND | BPF_K, CLONE_THREAD | CLONE_VM),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, CLONE_THREAD | CLONE_VM, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
    };
    struct sock_fprog program = {
        .len = (unsigned short)(sizeof(filter) / sizeof(filter[0])),
        .filter = filter,
    };
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0 ||
        prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program) != 0) {
        static const char message[] = "candidate seccomp initialization failed\n";
        (void)write(2, message, sizeof(message) - 1);
        _exit(126);
    }
    if (setenv("CONTENTOPS_SECCOMP_INSTALLED", "1", 1) != 0) {
        _exit(126);
    }
}
