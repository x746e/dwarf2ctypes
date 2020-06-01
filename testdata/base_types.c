struct base_types {
  char f_char;
  unsigned char f_uchar;
  short int f_short;
  short unsigned int f_ushort;
  int f_int;
  unsigned int f_uint;
  long int f_long;
  long unsigned int f_ulong;
  long long int f_longlong;
  long long unsigned int f_ulonglong;
} var1;

struct pointers_struct {
  // int* f_int_p;
  // void* f_void_p;
  const void* f_const_void;
} var2;

struct enum_struct {
  enum {a, b, c} f_enum_small;
  enum {d = 1l<<33, f} f_enum_big;
} var3;
