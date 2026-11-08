project('ephyra',
  version: '0.1.0',
  meson_version: '>= 1.0',
  license: 'AGPL-3.0-or-later',
)

base_id = 'de.nexumia.Ephyra'
# Nightly app next to the stable one (docs/release-channels.md).
nightly = get_option('profile') == 'development'
app_id = nightly ? base_id + '.Devel' : base_id

python = import('python').find_installation('python3')
pythondir = python.get_install_dir()

python.install_sources(
  'ephyra/__init__.py',
  'ephyra/__main__.py',
  'ephyra/api.py',
  'ephyra/browse.py',
  'ephyra/connection.py',
  'ephyra/demo.py',
  'ephyra/detail.py',
  'ephyra/images.py',
  'ephyra/keyring.py',
  'ephyra/main.py',
  'ephyra/playback.py',
  'ephyra/player.py',
  'ephyra/preferences.py',
  'ephyra/rotator.py',
  'ephyra/screen_off.py',
  'ephyra/segments.py',
  'ephyra/sessions.py',
  'ephyra/settings.py',
  'ephyra/setup.py',
  'ephyra/skipper.py',
  'ephyra/subtitle_view.py',
  'ephyra/subtitles.py',
  'ephyra/taps.py',
  'ephyra/text.py',
  'ephyra/track_sheet.py',
  'ephyra/upnext.py',
  'ephyra/widgets.py',
  'ephyra/window.py',
  subdir: 'ephyra',
)
# Loaded next to the Python files, also from the source tree.
install_data('ephyra/style.css', install_dir: pythondir / 'ephyra')

conf = configuration_data()
conf.set('PYTHON', python.full_path())
conf.set('PYTHONDIR', get_option('prefix') / pythondir)
configure_file(
  input: 'data/ephyra.in',
  output: 'ephyra',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)

config = configuration_data()
config.set('APP_ID', app_id)
config.set('BUILD_LABEL', get_option('build_label'))
configure_file(
  input: 'ephyra/config.py.in',
  output: 'config.py',
  configuration: config,
  install: true,
  install_dir: pythondir / 'ephyra',
)

if nightly
  # The stable files in data/ stay the only source; the nightly app gets
  # its own id and the name "Home Cinema (Nightly)".
  sed = find_program('sed')
  variant = [sed, '-e', 's/' + base_id + '/' + app_id + '/g',
             '-e', 's/^Name=Home Cinema$/Name=Home Cinema (Nightly)/',
             '-e', 's|<name>Home Cinema</name>|<name>Home Cinema (Nightly)</name>|',
             '@INPUT@']
  desktop = configure_file(input: 'data' / base_id + '.desktop',
    output: app_id + '.desktop', command: variant, capture: true)
  metainfo = configure_file(input: 'data' / base_id + '.metainfo.xml',
    output: app_id + '.metainfo.xml', command: variant, capture: true)
else
  desktop = files('data' / base_id + '.desktop')
  metainfo = files('data' / base_id + '.metainfo.xml')
endif
install_data(desktop, install_dir: get_option('datadir') / 'applications')
install_data(metainfo, install_dir: get_option('datadir') / 'metainfo')
install_data('data/icons' / base_id + '.svg',
  install_dir: get_option('datadir') / 'icons/hicolor/scalable/apps',
  rename: app_id + '.svg')

desktop_file_validate = find_program('desktop-file-validate', required: false)
if desktop_file_validate.found()
  test('validate-desktop', desktop_file_validate, args: [desktop])
endif
appstreamcli = find_program('appstreamcli', required: false)
if appstreamcli.found()
  test('validate-metainfo', appstreamcli,
    args: ['validate', '--no-net', metainfo])
endif
