#include <stdio.h>
#include <stdarg.h>
static FILE *getter_log_file;
void getter_core_log_set_path(const char *path) {
    if (getter_log_file) fclose(getter_log_file);
    getter_log_file = fopen(path, "w");
}
/* Native variadic libretro logger; logging only, no emulated-memory access. */
void getter_core_log(int level, const char *format, ...) {
    va_list args;
    fprintf(stderr, "CORELOG[%d] ", level);
    va_start(args, format);
    if (getter_log_file) {
        va_list copy;
        va_copy(copy, args);
        fprintf(getter_log_file, "CORELOG[%d] ", level);
        vfprintf(getter_log_file, format, copy);
        fflush(getter_log_file);
        va_end(copy);
    }
    vfprintf(stderr, format, args);
    va_end(args);
    fflush(stderr);
}
