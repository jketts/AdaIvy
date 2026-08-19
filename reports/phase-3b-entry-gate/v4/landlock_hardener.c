#define _GNU_SOURCE

typedef unsigned long size_t;
extern long syscall(long, ...);
extern int prctl(int, unsigned long, unsigned long, unsigned long, unsigned long);
extern int open(const char *, int, ...);
extern int close(int);
extern void _exit(int);

#define O_CLOEXEC 02000000
#define O_PATH 010000000
#define PR_SET_NO_NEW_PRIVS 38
#define SYS_LANDLOCK_CREATE_RULESET 444
#define SYS_LANDLOCK_ADD_RULE 445
#define SYS_LANDLOCK_RESTRICT_SELF 446
#define LANDLOCK_RULE_PATH_BENEATH 1
#define LANDLOCK_ACCESS_FS_EXECUTE (1ULL << 0)

struct landlock_ruleset_attr {
    unsigned long long handled_access_fs;
};

struct landlock_path_beneath_attr {
    unsigned long long allowed_access;
    int parent_fd;
};

/* Runs after the trusted ELF loader maps dependencies, before Lean's main. */
__attribute__((constructor)) static void tighten_execute_policy(void) {
    struct landlock_ruleset_attr ruleset = { LANDLOCK_ACCESS_FS_EXECUTE };
    struct landlock_path_beneath_attr rule;
    int ruleset_fd;
    int lean_fd;

    ruleset_fd = (int)syscall(SYS_LANDLOCK_CREATE_RULESET, &ruleset,
                              sizeof(ruleset), 0);
    if (ruleset_fd < 0)
        _exit(74);
    lean_fd = open("/opt/lean/bin/lean", O_PATH | O_CLOEXEC);
    if (lean_fd < 0)
        _exit(75);
    rule.allowed_access = LANDLOCK_ACCESS_FS_EXECUTE;
    rule.parent_fd = lean_fd;
    if (syscall(SYS_LANDLOCK_ADD_RULE, ruleset_fd,
                LANDLOCK_RULE_PATH_BENEATH, &rule, 0) < 0)
        _exit(76);
    close(lean_fd);
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) < 0)
        _exit(77);
    if (syscall(SYS_LANDLOCK_RESTRICT_SELF, ruleset_fd, 0) < 0)
        _exit(78);
    close(ruleset_fd);
}
