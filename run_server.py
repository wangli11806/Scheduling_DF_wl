import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import app as app_module
app_module.init_db()
app_module.app.run(host='0.0.0.0', port=5000, debug=False, threaded=True, use_reloader=False)
