import curses
import time
import random
import threading


def loading_bar(stdscr, start_row, start_col, length, speed=0.1, color_pair=2):
   stdscr.addstr(start_row, start_col, "[", curses.color_pair(color_pair))
   stdscr.addstr(start_row, start_col + length + 1, "]", curses.color_pair(color_pair))
   for i in range(1, length + 1):
       stdscr.addstr(start_row, start_col + i, "#", curses.color_pair(color_pair))
       stdscr.refresh()
       time.sleep(speed)


def display_step(stdscr, step_text, row, col, color):
   stdscr.addstr(row, col, step_text, curses.color_pair(color))
   stdscr.refresh()


def glitch_effect(stdscr, row, col, width, color_pair=2):
   chars = ['$', '%', '@', '#', '!', '^', '&', '*']
   for _ in range(random.randint(5, 15)):
       stdscr.addstr(row, col + random.randint(0, width), random.choice(chars), curses.color_pair(random.randint(1, 6)))
       stdscr.refresh()
       time.sleep(random.uniform(0.02, 0.1))


def matrix_effect(stdscr, cols, rows, color_pair=2):
   drops = [0] * cols
   while True:
       for i in range(cols):
           if random.random() > 0.9:
               drops[i] = 0
           char = str(random.randint(0, 1))
           stdscr.addstr(drops[i], i, char, curses.color_pair(color_pair))
           drops[i] += 1
           if drops[i] >= rows:
               drops[i] = 0
       stdscr.refresh()
       time.sleep(0.05)


def display_main_message(stdscr, message, row, col, color_pair=2):
   stdscr.addstr(row, col, message, curses.color_pair(color_pair) | curses.A_BOLD)
   stdscr.refresh()


def moving_dots(stdscr, message, row, col, color_pair=2):
   while True:
       for i in range(10):
           dots = '.' * i + ' ' * (10 - i)
           stdscr.addstr(row, col, message + dots, curses.color_pair(color_pair) | curses.A_BOLD)
           stdscr.refresh()
           time.sleep(0.2)


def hacking_sequence(stdscr):
   curses.start_color()
   curses.use_default_colors()
   curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
   curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
   curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)
   curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK)
   curses.init_pair(5, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
   curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_BLACK)


   stdscr.bkgd(' ', curses.color_pair(2))  # Set the background color to black using color pair 2 (Green text on Black)
   stdscr.clear()
   stdscr.refresh()


   main_message = "Starting Endgame Arb System"
   moving_dots_thread = threading.Thread(target=moving_dots, args=(stdscr, main_message, 0, 0, 3))
   moving_dots_thread.daemon = True
   moving_dots_thread.start()
   time.sleep(2)  # Adjusted time


   rows, cols = stdscr.getmaxyx()


   matrix_thread = threading.Thread(target=matrix_effect, args=(stdscr, cols, rows, 2))
   matrix_thread.daemon = True
   matrix_thread.start()


   stdscr.addstr(1, 0, "01001000 01000001 01000011 01001011 01001001 01001110 01000111", curses.color_pair(1))
   stdscr.addstr(2, 0, "01000010 01001001 01001110 01000001 01010010 01011001", curses.color_pair(1))
   stdscr.addstr(3, 0, "00110001 00110001 00110001 00110010 00110011 00110100 00110101 00110110 00110111", curses.color_pair(1))
   stdscr.addstr(4, 0, "00110010 00110011 00110100 00110101 00110110 00110111 00110011 00110010 00110011", curses.color_pair(1))
   stdscr.addstr(5, 0, "00110001 00110010 00110011 00110100 00110101 00110110 00110111 00110111 00110110", curses.color_pair(1))
   stdscr.addstr(6, 0, "00110010 00110011 00110100 00110101 00110110 00110111 00110011 00110010 00110011", curses.color_pair(1))
   stdscr.addstr(7, 0, "00110001 00110010 00110011 00110100 00110101 00110110 00110111 00110111 00110110", curses.color_pair(1))
   stdscr.addstr(8, 0, "00110010 00110011 00110100 00110101 00110110 00110111 00110011 00110010 00110011", curses.color_pair(1))
   stdscr.refresh()
   time.sleep(1)


   stdscr.addstr(9, 0, "Initiating Mainnet Hack...", curses.color_pair(3))
   stdscr.refresh()
   time.sleep(1)


   steps = [
       ("Connecting to Ethereum Mainnet...", 1),
       ("Bypassing security protocols...", 2),
       ("Injecting smart contract...", 3),
       ("Executing arbitrage trading...", 4),
       ("Fetching wallet balances...", 5),
       ("Validating transactions...", 1),
       ("Compiling profit reports...", 2),
       ("Scanning...", 3)
   ]


   for i, (step, color) in enumerate(steps):
       display_step(stdscr, step, i + 10, 0, color)
       loading_bar(stdscr, i + 10, len(step) + 1, 20, speed=random.uniform(0.15, 0.3), color_pair=2)
       glitch_effect(stdscr, i + 10, len(step) + 23, 10, color_pair=2)
       stdscr.addstr(i + 10, len(step) + 23, "[DONE]", curses.color_pair(2))
       stdscr.refresh()
       time.sleep(random.uniform(0.5, 1))  # Adjusted time


   stdscr.addstr(len(steps) + 11, 0, "Hack completed successfully!", curses.color_pair(2))
   stdscr.refresh()
   stdscr.getch()


def main():
   curses.wrapper(hacking_sequence)


if __name__ == "__main__":
   main()

