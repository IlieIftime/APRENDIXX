"""Allow ``python -m aprendix`` to launch the GUI with CLI fallback."""

import sys

if sys.platform == "ios":
    from aprendix_mobile.toga_app import main

    main().main_loop()
else:
    from aprendix.bootstrap import gui_main

    raise SystemExit(gui_main())
