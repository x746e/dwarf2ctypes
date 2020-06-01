struct union_struct {
  union {
    char f_char;
    short f_short;
  } f_union;
} var1;

struct anon_union_struct {
  union {
    char f_char;
    short f_short;
  };
} var2;

struct nested_anon_union_struct {
  union {
    char f_char;
    union {
      short f_short;
      int f_int;
    };
  };
} var3;
