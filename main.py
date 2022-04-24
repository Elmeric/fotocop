from multiprocessing import freeze_support

from fotocop.__init__ import run_main


if __name__ == '__main__':
    freeze_support()
    run_main()
