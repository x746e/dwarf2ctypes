struct set;

struct object {
  struct set *set;
} var1;

struct set {
  struct object obj;
} var2;
