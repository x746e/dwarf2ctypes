struct bitfield_struct {
  int f_before;
  int f_bit1 : 1,
      f_bit2 : 2,
      f_bit3 : 3;
  int f_after;
} var;

// Doesn't seem like it's supported by ctypes.
// struct bitfield_with_nested_struct {
//   int f_x : 1;
//   struct {
//     short f_z : 1;
//   };
// } var4;

struct winsize {
      unsigned short ws_row;
      unsigned short ws_col;
      unsigned short ws_xpixel;
      unsigned short ws_ypixel;
};

#define BITS_PER_LONG 64

struct tty_struct {
	unsigned long flags;
	int count;
	struct winsize winsize;		/* winsize_mutex */
	unsigned long stopped:1,	/* flow_lock */
		      flow_stopped:1,
		      unused:BITS_PER_LONG - 2;
	int hw_stopped;
} var5;
