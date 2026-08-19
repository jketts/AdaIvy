#define _GNU_SOURCE

/* Phase 3B dynamic-input entry-gate v5 launcher: Linux/AArch64 only. */

typedef unsigned long size_t;
typedef long ssize_t;
typedef int pid_t;

extern long syscall(long, ...);
extern int prctl(int, unsigned long, unsigned long, unsigned long, unsigned long);
extern int open(const char *, int, ...);
extern int close(int);
extern ssize_t read(int, void *, size_t);
extern ssize_t write(int, const void *, size_t);
extern int fchmod(int, unsigned int);
extern int pipe(int[2]);
extern pid_t fork(void);
extern int waitpid(pid_t, int *, int);
extern int execve(const char *, char *const[], char *const[]);
extern void _exit(int);
extern int printf(const char *, ...);
extern int puts(const char *);
extern int strcmp(const char *, const char *);
extern int *__errno_location(void);

#define ERRNO (*__errno_location())
#define EPERM 1
#define EINTR 4
#define EACCES 13
#define O_RDONLY 0
#define O_WRONLY 1
#define O_CREAT 0100
#define O_EXCL 0200
#define O_TRUNC 01000
#define O_NOFOLLOW 0400000
#define O_CLOEXEC 02000000
#define O_PATH 010000000
#define AT_EMPTY_PATH 0x1000

#define PR_SET_NO_NEW_PRIVS 38
#define PR_SET_SECCOMP 22
#define SECCOMP_MODE_FILTER 2
#define SECCOMP_RET_KILL_PROCESS 0x80000000U
#define SECCOMP_RET_ALLOW 0x7fff0000U
#define SECCOMP_RET_ERRNO 0x00050000U

#define BPF_LD 0x00
#define BPF_W 0x00
#define BPF_ABS 0x20
#define BPF_JMP 0x05
#define BPF_JEQ 0x10
#define BPF_K 0x00
#define BPF_RET 0x06
#define AUDIT_ARCH_AARCH64 0xc00000b7U

#define SYS_MEMFD_CREATE 279
#define SYS_EXECVEAT 281
#define SYS_LANDLOCK_CREATE_RULESET 444
#define SYS_LANDLOCK_ADD_RULE 445
#define SYS_LANDLOCK_RESTRICT_SELF 446

#define LANDLOCK_CREATE_RULESET_VERSION 1
#define LANDLOCK_RULE_PATH_BENEATH 1
#define LANDLOCK_ACCESS_FS_EXECUTE (1ULL << 0)

#define MAX_INPUT_BYTES (256UL * 1024UL)

struct landlock_ruleset_attr {
    unsigned long long handled_access_fs;
};

struct landlock_path_beneath_attr {
    unsigned long long allowed_access;
    int parent_fd;
};

struct sock_filter {
    unsigned short code;
    unsigned char jt;
    unsigned char jf;
    unsigned int k;
};

struct sock_fprog {
    unsigned short len;
    struct sock_filter *filter;
};

#define STMT(c, v) ((struct sock_filter){(unsigned short)(c), 0, 0, (v)})
#define JUMP(c, v, t, f) ((struct sock_filter){(unsigned short)(c), (t), (f), (v)})

static const char *const lean_path = "/opt/lean/bin/lean";
static const char *const input_path = "/tmp/adaivy-input.lean";
static char *const clean_env[] = {
    "HOME=/nonexistent",
    "PATH=",
    "LEAN_PATH=/opt/mathlib/lib/lean:/opt/lean/lib/lean",
    "LD_PRELOAD=/checker/landlock_hardener.so",
    0
};

static int landlock_abi(void) {
    return (int)syscall(SYS_LANDLOCK_CREATE_RULESET, 0, 0,
                        LANDLOCK_CREATE_RULESET_VERSION);
}

static int add_execute_path(int ruleset_fd, const char *path) {
    struct landlock_path_beneath_attr path_rule;
    int path_fd = open(path, O_PATH | O_CLOEXEC);
    int result;
    if (path_fd < 0)
        return -1;
    path_rule.allowed_access = LANDLOCK_ACCESS_FS_EXECUTE;
    path_rule.parent_fd = path_fd;
    result = (int)syscall(SYS_LANDLOCK_ADD_RULE, ruleset_fd,
                          LANDLOCK_RULE_PATH_BENEATH, &path_rule, 0);
    close(path_fd);
    return result;
}

static int install_landlock(int bootstrap_loader) {
    struct landlock_ruleset_attr ruleset = { LANDLOCK_ACCESS_FS_EXECUTE };
    int ruleset_fd;

    ruleset_fd = (int)syscall(SYS_LANDLOCK_CREATE_RULESET, &ruleset,
                              sizeof(ruleset), 0);
    if (ruleset_fd < 0)
        return -1;
    if (add_execute_path(ruleset_fd, lean_path) < 0) {
        close(ruleset_fd);
        return -2;
    }
    if (bootstrap_loader &&
        add_execute_path(ruleset_fd, "/lib/ld-linux-aarch64.so.1") < 0) {
        close(ruleset_fd);
        return -3;
    }
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) < 0) {
        close(ruleset_fd);
        return -4;
    }
    if (syscall(SYS_LANDLOCK_RESTRICT_SELF, ruleset_fd, 0) < 0) {
        close(ruleset_fd);
        return -5;
    }
    close(ruleset_fd);
    return 0;
}

static int install_seccomp(void) {
    struct sock_filter filter[] = {
        STMT(BPF_LD | BPF_W | BPF_ABS, 4),
        JUMP(BPF_JMP | BPF_JEQ | BPF_K, AUDIT_ARCH_AARCH64, 1, 0),
        STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        STMT(BPF_LD | BPF_W | BPF_ABS, 0),
        JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_EXECVEAT, 0, 1),
        STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_MEMFD_CREATE, 0, 1),
        STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW)
    };
    struct sock_fprog program = {
        (unsigned short)(sizeof(filter) / sizeof(filter[0])), filter
    };
    return prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER,
                 (unsigned long)&program, 0, 0);
}

static int write_all(int fd, const char *data, size_t length) {
    size_t offset = 0;
    while (offset < length) {
        ssize_t written = write(fd, data + offset, length - offset);
        if (written < 0 && ERRNO == EINTR)
            continue;
        if (written <= 0)
            return -1;
        offset += (size_t)written;
    }
    return 0;
}

static int stage_stdin(void) {
    char buffer[8192];
    size_t total = 0;
    int output = open(input_path,
                      O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC,
                      0600);
    if (output < 0)
        return 66;
    for (;;) {
        ssize_t got = read(0, buffer, sizeof(buffer));
        if (got < 0 && ERRNO == EINTR)
            continue;
        if (got < 0) {
            close(output);
            return 67;
        }
        if (got == 0)
            break;
        if ((size_t)got > MAX_INPUT_BYTES - total) {
            close(output);
            return 68;
        }
        if (write_all(output, buffer, (size_t)got) < 0) {
            close(output);
            return 69;
        }
        total += (size_t)got;
    }
    if (total == 0) {
        close(output);
        return 65;
    }
    if (fchmod(output, 0400) < 0) {
        close(output);
        return 69;
    }
    close(output);
    return 0;
}

static int child_exec_errno(const char *path) {
    int fds[2];
    int status;
    int child_errno = 0;
    pid_t pid;
    char *const argv[] = { (char *)path, 0 };
    if (pipe(fds) < 0)
        return -100;
    pid = fork();
    if (pid == 0) {
        close(fds[0]);
        execve(path, argv, clean_env);
        child_errno = ERRNO;
        (void)write(fds[1], &child_errno, sizeof(child_errno));
        _exit(127);
    }
    close(fds[1]);
    if (pid < 0) {
        close(fds[0]);
        return -101;
    }
    (void)read(fds[0], &child_errno, sizeof(child_errno));
    close(fds[0]);
    (void)waitpid(pid, &status, 0);
    return child_errno;
}

static int copy_for_probe(const char *destination, int script) {
    char buffer[8192];
    ssize_t got;
    int source = -1;
    int output;
    if (!script)
        source = open("/checker/launcher", O_RDONLY | O_CLOEXEC);
    output = open(destination, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0700);
    if (output < 0)
        return -1;
    if (script) {
        static const char line[] = "#!/checker/launcher\n";
        if (write(output, line, sizeof(line) - 1) != (ssize_t)(sizeof(line) - 1)) {
            close(output);
            return -2;
        }
    } else {
        if (source < 0) {
            close(output);
            return -3;
        }
        while ((got = read(source, buffer, sizeof(buffer))) > 0)
            if (write(output, buffer, (size_t)got) != got) {
                close(source);
                close(output);
                return -4;
            }
        close(source);
    }
    if (fchmod(output, 0700) < 0) {
        close(output);
        return -5;
    }
    close(output);
    return 0;
}

static int execveat_errno(void) {
    int fd = open(lean_path, O_PATH | O_CLOEXEC);
    char *const argv[] = { (char *)lean_path, "--version", 0 };
    int result;
    if (fd < 0)
        return ERRNO;
    result = (int)syscall(SYS_EXECVEAT, fd, "", argv, clean_env, AT_EMPTY_PATH);
    close(fd);
    return result < 0 ? ERRNO : 0;
}

static int memfd_errno(void) {
    int result = (int)syscall(SYS_MEMFD_CREATE, "adaivy-v5-probe", 0);
    if (result >= 0) {
        close(result);
        return 0;
    }
    return ERRNO;
}

static int policy_self_test(int abi) {
    int sh = child_exec_errno("/bin/sh");
    int bash = child_exec_errno("/bin/bash");
    int env = child_exec_errno("/usr/bin/env");
    int launcher = child_exec_errno("/checker/launcher");
    int loader = child_exec_errno("/lib/ld-linux-aarch64.so.1");
    int tmp_copy_status = copy_for_probe("/tmp/copied-executable", 0);
    int tmp_copy = child_exec_errno("/tmp/copied-executable");
    int shebang_status = copy_for_probe("/tmp/shebang-probe", 1);
    int shebang = child_exec_errno("/tmp/shebang-probe");
    int at = execveat_errno();
    int memfd = memfd_errno();
    int pass = (sh != 0 && bash != 0 && env != 0 && launcher != 0 &&
                loader != 0 && tmp_copy_status == 0 && tmp_copy != 0 &&
                shebang_status == 0 && shebang != 0 && at == EPERM &&
                memfd == EPERM);
    printf("{\"schema_version\":\"adaivy.landlock-policy-probe.v2\"," 
           "\"landlock_abi\":%d,\"fixed_input_path\":\"%s\"," 
           "\"max_input_bytes\":%lu,\"passed\":%s," 
           "\"attempts\":{\"/bin/sh\":%d,\"/bin/bash\":%d," 
           "\"/usr/bin/env\":%d,\"/checker/launcher\":%d," 
           "\"/lib/ld-linux-aarch64.so.1\":%d," 
           "\"tmpfs_copy_setup\":%d,\"tmpfs_copy\":%d," 
           "\"tmpfs_shebang_setup\":%d,\"tmpfs_shebang\":%d," 
           "\"execveat\":%d,\"memfd_create\":%d}}\n",
           abi, input_path, MAX_INPUT_BYTES, pass ? "true" : "false",
           sh, bash, env, launcher, loader, tmp_copy_status, tmp_copy,
           shebang_status, shebang, at, memfd);
    return pass ? 0 : 1;
}

int main(int argc, char **argv) {
    int abi = landlock_abi();
    int result;
    char *lean_argv[5];
    if (argc == 2 && strcmp(argv[1], "--probe-landlock") == 0) {
        printf("{\"schema_version\":\"adaivy.landlock-abi.v1\"," 
               "\"architecture\":\"aarch64\",\"abi\":%d," 
               "\"execute_supported\":%s}\n",
               abi, abi >= 1 ? "true" : "false");
        return abi >= 1 ? 0 : 1;
    }
    if (argc > 1 && !(argc == 2 && strcmp(argv[1], "--policy-self-test") == 0)) {
        puts("path and argument input rejected; submit source on stdin");
        return 64;
    }
    if (abi < 1) {
        puts("landlock execute restriction unavailable");
        return 70;
    }
    result = install_landlock(!(argc == 2 &&
                                strcmp(argv[1], "--policy-self-test") == 0));
    if (result != 0) {
        printf("landlock installation failed: %d errno=%d\n", result, ERRNO);
        return 71;
    }
    if (install_seccomp() < 0) {
        printf("seccomp installation failed: errno=%d\n", ERRNO);
        return 72;
    }
    if (argc == 2)
        return policy_self_test(abi);
    result = stage_stdin();
    if (result != 0) {
        printf("stdin ingestion rejected: code=%d max_bytes=%lu path=%s\n",
               result, MAX_INPUT_BYTES, input_path);
        return result;
    }
    lean_argv[0] = (char *)lean_path;
    lean_argv[1] = "--json";
    lean_argv[2] = "--timeout=200000";
    lean_argv[3] = (char *)input_path;
    lean_argv[4] = 0;
    execve(lean_path, lean_argv, clean_env);
    printf("lean exec failed: errno=%d\n", ERRNO);
    return 73;
}
