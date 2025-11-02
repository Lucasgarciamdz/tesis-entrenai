#!/usr/bin/env bash
set -euo pipefail

MOODLE_SRC_DIR="/usr/src/moodle"
MOODLE_DIR="/var/www/html"
MOODLE_PUBLIC_SRC_DIR="$MOODLE_SRC_DIR/public"
MOODLE_PUBLIC_DIR="$MOODLE_DIR/public"
MOODLE_DATA_DIR="/var/moodledata"
BOOTSTRAP_SENTINEL="${BOOTSTRAP_SENTINEL:-$MOODLE_DATA_DIR/.bootstrap_fixtures_applied}"

# ensure apache env defaults are sensible
export APACHE_RUN_DIR="${APACHE_RUN_DIR:-/var/run/apache2}"
export APACHE_LOG_DIR="${APACHE_LOG_DIR:-/var/log/apache2}"
export LANG="${LANG:-en_US.UTF-8}"

gosu_exec() {
    if [ "$(id -u)" -eq 0 ]; then
        gosu www-data "$@"
    else
        "$@"
    fi
}

wait_for_db() {
    local retries=30
    local sleep_seconds=2
    local attempt=1

    export PGPASSWORD="${DB_PASS:-}"
    while ! pg_isready -h "${DB_HOST:-db}" -p "${DB_PORT:-5432}" -d "${DB_NAME:-moodle}" -U "${DB_USER:-moodle}" >/dev/null 2>&1; do
        if [ "$attempt" -ge "$retries" ]; then
            echo "Database connection still failing after $retries attempts." >&2
            exit 1
        fi
        attempt=$((attempt + 1))
        sleep "$sleep_seconds"
    done
}

initial_sync_code() {
    if [ ! -d "$MOODLE_DIR" ]; then
        mkdir -p "$MOODLE_DIR"
    fi

    if [ "$(find "$MOODLE_DIR" -mindepth 1 -print -quit 2>/dev/null)" ]; then
        return
    fi

    echo "Populating Moodle code volume from seed at $MOODLE_SRC_DIR"
    rsync -a --delete "$MOODLE_SRC_DIR"/ "$MOODLE_DIR"/
}

sync_wsmanagesections_plugin() {
    local plugin_name="wsmanagesections"
    local src_path="$MOODLE_PUBLIC_SRC_DIR/local/$plugin_name"
    local dest_path="$MOODLE_PUBLIC_DIR/local/$plugin_name"

    if [ ! -d "$src_path" ]; then
        echo "Source plugin directory $src_path not found; skipping $plugin_name deployment"
        return
    fi

    echo "Syncing $plugin_name plugin into Moodle codebase"
    mkdir -p "$dest_path"
    rsync -a --delete "$src_path"/ "$dest_path"/
}

prepare_data_dir() {
    mkdir -p "$MOODLE_DATA_DIR"
    chmod 770 "$MOODLE_DATA_DIR"
    chown -R www-data:www-data "$MOODLE_DATA_DIR"
}

run_install_if_needed() {
    local config_file="$MOODLE_DIR/config.php"

    if [ -f "$config_file" ]; then
        return
    fi

    echo "Running initial Moodle CLI installation"
    wait_for_db

    local wwwroot="${MOODLE_URL:-http://localhost:8080}"
    local dataroot="$MOODLE_DATA_DIR"
    local dbtype="${DB_TYPE:-pgsql}"
    local dbhost="${DB_HOST:-db}"
    local dbport="${DB_PORT:-5432}"
    local dbname="${DB_NAME:-moodle}"
    local dbuser="${DB_USER:-moodle}"
    local dbpass="${DB_PASS:-moodlepass}"
    local fullname="${SITE_FULLNAME:-Moodle 5 Site}"
    local shortname="${SITE_SHORTNAME:-M5}"
    local adminuser="${ADMIN_USER:-admin}"
    local adminpass="${ADMIN_PASS:-ChangeMe!123}"
    local adminemail="${ADMIN_EMAIL:-admin@example.com}"

    (cd "$MOODLE_DIR" && \
        gosu_exec php admin/cli/install.php \
            --wwwroot="${wwwroot}" \
            --dataroot="${dataroot}" \
            --dbtype="${dbtype}" \
            --dbhost="${dbhost}" \
            --dbport="${dbport}" \
            --dbname="${dbname}" \
            --dbuser="${dbuser}" \
            --dbpass="${dbpass}" \
            --fullname="${fullname}" \
            --shortname="${shortname}" \
            --adminuser="${adminuser}" \
            --adminpass="${adminpass}" \
            --adminemail="${adminemail}" \
            --non-interactive \
            --agree-license)

    chown www-data:www-data "$config_file"
}

apply_post_install_config() {
    (cd "$MOODLE_DIR" && \
        gosu_exec php <<'PHP'
<?php
define('CLI_SCRIPT', true);

require 'config.php';

# Ensure global web services are enabled.
set_config('enablewebservices', 1);

$current = (string)get_config('core', 'enabledwsprotocols');
$normalized = str_replace(["\r", "\n"], ',', $current);
$normalized = str_replace(' ', '', $normalized);
$protocols = array_filter(array_values(array_unique(explode(',', $normalized))), 'strlen');
if (!in_array('rest', $protocols, true)) {
    $protocols[] = 'rest';
}
set_config('enabledwsprotocols', implode(',', $protocols));
set_config('rest', '1', 'webserviceprotocols');
set_config('rest_enabled', '1', 'webserviceprotocols');
set_config('enabled', '1', 'webservice_rest');
set_config('disabled', '0', 'webservice_rest');
set_config('enableprotocols', 'rest');
PHP
    )
}

run_upgrade() {
    (cd "$MOODLE_DIR" && \
        gosu_exec php admin/cli/upgrade.php --non-interactive)
}

ensure_entrenai_user() {
    local username="entrenai_user"
    local firstname="Entrenai"
    local lastname="UM"
    local email="entrenai@um.edu.ar"
    local credspath="$MOODLE_DATA_DIR/entrenai_user_credentials.txt"
    local requested_password="${ENTRENAI_USER_PASSWORD:-ChangeMe!123}"
    local attempt=1
    local max_attempts=30
    local sleep_seconds=2
    local status result password

    while [ "$attempt" -le "$max_attempts" ]; do
        set +e
        result=$(
            cd "$MOODLE_DIR" &&
            ENTRENAI_USER_PASSWORD="$requested_password" gosu_exec php <<'PHP'
<?php
define('CLI_SCRIPT', true);

require 'config.php';
require_once $CFG->libdir . '/moodlelib.php';
require_once $CFG->libdir . '/weblib.php';
require_once $CFG->dirroot . '/user/lib.php';

$username = 'entrenai_user';
$firstname = 'Entrenai';
$lastname = 'UM';
$email = 'entrenai@um.edu.ar';

$password = getenv('ENTRENAI_USER_PASSWORD');
if ($password === false || $password === '') {
    $password = 'ChangeMe!123';
}
$user = \core_user::get_user_by_username($username);
if ($user) {
    $needsupdate = false;
    if ($user->firstname !== $firstname) {
        $user->firstname = $firstname;
        $needsupdate = true;
    }
    if ($user->lastname !== $lastname) {
        $user->lastname = $lastname;
        $needsupdate = true;
    }
    if ($user->email !== $email) {
        $user->email = $email;
        $needsupdate = true;
    }
    if ($needsupdate) {
        user_update_user($user, false);
    }
    $passwordchanged = empty($user->password) || !password_verify($password, $user->password);
    if ($passwordchanged) {
        update_internal_user_password($user, $password);
    }
    if ($passwordchanged) {
        echo "UPDATED:$password\n";
    } else {
        echo "EXISTS\n";
    }
    exit(0);
}
$now = time();

try {
    $city = core_user::get_property_default('city');
} catch (Throwable $e) {
    $city = $CFG->defaultcity ?? '';
}

try {
    $country = core_user::get_property_default('country');
} catch (Throwable $e) {
    $country = $CFG->country ?? '';
}

try {
    $lang = core_user::get_property_default('lang');
} catch (Throwable $e) {
    $lang = get_newuser_language();
}

try {
    $calendartype = core_user::get_property_default('calendartype');
} catch (Throwable $e) {
    $calendartype = $CFG->calendartype ?? 'gregorian';
}

try {
    $theme = core_user::get_property_default('theme');
} catch (Throwable $e) {
    $theme = '';
}

try {
    $timezone = core_user::get_property_default('timezone');
} catch (Throwable $e) {
    $timezone = core_date::get_server_timezone();
}

try {
    $maildisplay = core_user::get_property_default('maildisplay');
} catch (Throwable $e) {
    $maildisplay = $CFG->defaultpreference_maildisplay ?? 2;
}

try {
    $mailformat = core_user::get_property_default('mailformat');
} catch (Throwable $e) {
    $mailformat = $CFG->defaultpreference_mailformat ?? 1;
}

try {
    $maildigest = core_user::get_property_default('maildigest');
} catch (Throwable $e) {
    $maildigest = $CFG->defaultpreference_maildigest ?? 0;
}

try {
    $autosubscribe = core_user::get_property_default('autosubscribe');
} catch (Throwable $e) {
    $autosubscribe = $CFG->defaultpreference_autosubscribe ?? 1;
}

try {
    $trackforums = core_user::get_property_default('trackforums');
} catch (Throwable $e) {
    $trackforums = $CFG->defaultpreference_trackforums ?? 1;
}

$newuser = (object) [
    'auth' => 'manual',
    'confirmed' => 1,
    'policyagreed' => 0,
    'deleted' => 0,
    'suspended' => 0,
    'mnethostid' => $CFG->mnet_localhost_id,
    'username' => $username,
    'password' => $password,
    'idnumber' => '',
    'firstname' => $firstname,
    'lastname' => $lastname,
    'surname' => $lastname,
    'email' => $email,
    'emailstop' => 0,
    'phone1' => '',
    'phone2' => '',
    'institution' => '',
    'department' => '',
    'address' => '',
    'city' => $city ?? '',
    'country' => $country ?? '',
    'lang' => $lang ?? get_newuser_language(),
    'calendartype' => $calendartype ?? 'gregorian',
    'theme' => $theme ?? '',
    'timezone' => $timezone ?? core_date::get_server_timezone(),
    'firstaccess' => 0,
    'lastaccess' => 0,
    'lastlogin' => 0,
    'currentlogin' => 0,
    'lastip' => '',
    'secret' => random_string(15),
    'picture' => 0,
    'description' => '',
    'descriptionformat' => FORMAT_HTML,
    'maildisplay' => $maildisplay,
    'mailformat' => $mailformat,
    'maildigest' => $maildigest,
    'autosubscribe' => $autosubscribe,
    'trackforums' => $trackforums,
    'timecreated' => $now,
    'timemodified' => $now,
    'trustbitmask' => 0,
    'imagealt' => '',
    'lastnamephonetic' => '',
    'firstnamephonetic' => '',
    'middlename' => '',
    'alternatename' => '',
];

$newuser->id = user_create_user($newuser, true);

echo "CREATED:$password\n";
PHP
        )
        status=$?
        set -e

        if [ "$status" -eq 0 ]; then
            result=$(printf "%s" "$result" | tr -d '\r')
            if [[ "$result" == CREATED:* ]]; then
                password=${result#CREATED:}
                printf 'username: %s\npassword: %s\nemail: %s\n' \
                    "$username" "$password" "$email" > "$credspath"
                chown www-data:www-data "$credspath"
                chmod 600 "$credspath"
                echo "Created user $username with password stored at $credspath"
                return
            elif [[ "$result" == UPDATED:* ]]; then
                password=${result#UPDATED:}
                printf 'username: %s\npassword: %s\nemail: %s\n' \
                    "$username" "$password" "$email" > "$credspath"
                chown www-data:www-data "$credspath"
                chmod 600 "$credspath"
                echo "Updated user $username with password stored at $credspath"
                return
            elif [[ "$result" == EXISTS* ]]; then
                echo "User $username already exists; profile ensured."
                if [ -f "$credspath" ]; then
                    chown www-data:www-data "$credspath"
                    chmod 600 "$credspath"
                fi
                return
            fi
        fi

        if [ -n "$result" ]; then
            echo "Entrenai_user provisioning output: $result"
        fi

        if [ "$attempt" -ge "$max_attempts" ]; then
            echo "Failed to provision Entrenai_user after $max_attempts attempts" >&2
            return 1
        fi

        echo "Entrenai_user provisioning attempt $attempt failed; retrying in $sleep_seconds seconds"
        attempt=$((attempt + 1))
        sleep "$sleep_seconds"
    done
}

ensure_entrenai_external_service() {
    local shortname="entrenai_api"
    local servicename="Entrenai API"

    (cd "$MOODLE_DIR" && \
        gosu_exec php <<'PHP'
<?php
define('CLI_SCRIPT', true);

require 'config.php';
require_once $CFG->libdir . '/accesslib.php';
require_once $CFG->dirroot . '/user/lib.php';

global $DB;

$shortname = 'entrenai_api';
$servicename = 'Entrenai API';
$now = time();

$current = (string)get_config('core', 'enabledwsprotocols');
$normalized = str_replace(["\r", "\n"], ',', $current);
$normalized = str_replace(' ', '', $normalized);
$protocols = array_filter(array_values(array_unique(explode(',', $normalized))), 'strlen');
if (!in_array('rest', $protocols, true)) {
    $protocols[] = 'rest';
}
set_config('enabledwsprotocols', implode(',', $protocols));
set_config('rest', '1', 'webserviceprotocols');
set_config('rest_enabled', '1', 'webserviceprotocols');
set_config('enabled', '1', 'webservice_rest');
set_config('disabled', '0', 'webservice_rest');
set_config('enableprotocols', 'rest');

$desired = [
    'name' => $servicename,
    'shortname' => $shortname,
    'component' => '',
    'enabled' => 1,
    'requiredcapability' => '',
    'restrictedusers' => 1,
    'iprestriction' => '',
    'tokenusers' => 0,
    'downloadfiles' => 1,
    'uploadfiles' => 1,
];

$service = $DB->get_record('external_services', ['shortname' => $shortname]);

if ($service) {
    $needsupdate = false;
    foreach ($desired as $field => $value) {
        if (!property_exists($service, $field) || (string)$service->$field !== (string)$value) {
            $service->$field = $value;
            $needsupdate = true;
        }
    }
    if ($needsupdate) {
        $service->timemodified = $now;
        $DB->update_record('external_services', $service);
        echo "UPDATED:$shortname\n";
    } else {
        echo "EXISTS:$shortname\n";
    }
} else {
    $service = (object)$desired;
    $service->timecreated = $now;
    $service->timemodified = $now;
    $service->id = $DB->insert_record('external_services', $service);
    echo "CREATED:$shortname\n";
}

$desiredfunctions = [
    'local_wsmanagesections_create_sections',
    'local_wsmanagesections_get_sections',
    'local_wsmanagesections_move_section',
    'local_wsmanagesections_update_sections',
    'mod_workshop_update_assessment',
    'core_enrol_get_users_courses',
    'core_course_get_contents',
    'core_course_get_course_module',
];

$existingfunctions = $DB->get_records_menu('external_services_functions', ['externalserviceid' => $service->id], '', 'functionname,id');

foreach ($desiredfunctions as $functionname) {
    if (!$DB->record_exists('external_functions', ['name' => $functionname])) {
        echo "MISSINGFUNCTION:$functionname\n";
        continue;
    }

    if (!isset($existingfunctions[$functionname])) {
        $record = (object)[
            'externalserviceid' => $service->id,
            'functionname' => $functionname,
        ];
        $DB->insert_record('external_services_functions', $record);
        echo "FUNCTION_ATTACHED:$functionname\n";
    }
}

$entrenaiuser = \core_user::get_user_by_username('entrenai_user');

if ($entrenaiuser) {
    $serviceuser = $DB->get_record('external_services_users', [
        'externalserviceid' => $service->id,
        'userid' => $entrenaiuser->id,
    ]);

    if (!$serviceuser) {
        $now = time();
        $serviceuser = (object)[
            'externalserviceid' => $service->id,
            'userid' => $entrenaiuser->id,
            'timecreated' => $now,
            'validuntil' => 0,
            'iprestriction' => '',
        ];
        $DB->insert_record('external_services_users', $serviceuser);
        echo "SERVICE_USER_ATTACHED:{$entrenaiuser->username}\n";
    }

    $role = $DB->get_record('role', ['shortname' => 'entrenai_api']);
    if (!$role) {
        $roleid = create_role($servicename . ' role', 'entrenai_api', 'Capabilities for Entrenai API service user');
        $role = $DB->get_record('role', ['id' => $roleid], '*', MUST_EXIST);
        echo "ROLE_CREATED:{$role->shortname}\n";
    }

    $capabilities = [
        'moodle/course:update',
        'moodle/course:movesections',
        'moodle/course:view',
        'moodle/course:viewparticipants',

    ];

    $systemcontext = context_system::instance();
    foreach ($capabilities as $capability) {
        assign_capability($capability, CAP_ALLOW, $role->id, $systemcontext, true);
    }

    if (!user_has_role_assignment($entrenaiuser->id, $role->id, $systemcontext->id)) {
        role_assign($role->id, $entrenaiuser->id, $systemcontext->id);
        echo "ROLE_ASSIGNED:{$role->shortname}:{$entrenaiuser->username}\n";
    }

    $token = $DB->get_record('external_tokens', [
        'tokentype' => EXTERNAL_TOKEN_PERMANENT,
        'userid' => $entrenaiuser->id,
        'externalserviceid' => $service->id,
    ], '*', IGNORE_MULTIPLE);

    $tokenvalue = 'entrenai_api_token';

    $usercontext = context_user::instance($entrenaiuser->id, IGNORE_MISSING);
    if (!$usercontext) {
        $usercontext = context_user::instance($entrenaiuser->id);
    }

    if ($token) {
        if ($token->token !== $tokenvalue || $token->validuntil != 0 || (int)$token->enabled !== 1 || (string)$token->iprestriction !== '' || (int)$token->contextid !== (int)$usercontext->id) {
            $token->token = $tokenvalue;
            $token->validuntil = 0;
            $token->enabled = 1;
            $token->iprestriction = '';
            $token->privatetoken = random_string(32);
            $token->timemodified = time();
            $token->contextid = $usercontext->id;
            $DB->update_record('external_tokens', $token);
            echo "TOKEN_UPDATED:$tokenvalue\n";
        }
    } else {
        $token = (object)[
            'externalserviceid' => $service->id,
            'userid' => $entrenaiuser->id,
            'tokentype' => EXTERNAL_TOKEN_PERMANENT,
            'token' => $tokenvalue,
            'validuntil' => 0,
            'iprestriction' => '',
            'sid' => '',
            'privatetoken' => random_string(32),
            'timecreated' => time(),
            'creatorid' => $entrenaiuser->id,
            'lastaccess' => 0,
            'expired' => 0,
            'enabled' => 1,
            'contextid' => $usercontext->id,
        ];
        $DB->insert_record('external_tokens', $token);
        echo "TOKEN_CREATED:$token\n";
    }
} else {
    echo "MISSINGUSER:entrenai_user\n";
}
PHP
    )
}

apply_bootstrap_fixtures() {
    if [ "${BOOTSTRAP_FIXTURES:-0}" != "1" ]; then
        return
    fi

    if [ -f "$BOOTSTRAP_SENTINEL" ]; then
        echo "Bootstrap fixtures already applied (marker: $BOOTSTRAP_SENTINEL)."
        return
    fi

    echo "Applying bootstrap fixtures"
    local applied=false

    if [ -f /bootstrap/users.csv ]; then
        (cd "$MOODLE_DIR" && \
            gosu_exec php admin/tool/uploaduser/cli/uploaduser.php \
                --file=/bootstrap/users.csv \
                --mode=updateorcreate \
                --passwordpolicy=0 \
                --allowduplicateemails=1)
        applied=true
    else
        echo "No /bootstrap/users.csv found; skipping user import"
    fi

    (cd "$MOODLE_DIR" && \
        gosu_exec php admin/tool/generator/cli/maketestcourse.php \
            --shortname="${FIXTURE_COURSE_SHORTNAME:-Demo101}" \
            --fullname="${FIXTURE_COURSE_FULLNAME:-Demo 101}" \
            --size="${FIXTURE_COURSE_SIZE:-S}")
    applied=true

    # Example plugin bootstrap (uncomment and adapt paths/names to enable):
    # if [ -f /bootstrap/plugins/local_example.zip ]; then
    #     tmpdir=$(mktemp -d)
    #     unzip /bootstrap/plugins/local_example.zip -d "$tmpdir"
    #     rsync -a "$tmpdir"/local/example "$MOODLE_DIR/local/"
    #     rm -rf "$tmpdir"
    #     (cd "$MOODLE_DIR" && \
    #         gosu_exec php admin/cli/upgrade.php --non-interactive)
    #     applied=true
    # fi

    if [ -d /bootstrap/plugins ]; then
        echo "Detected /bootstrap/plugins. To install, place plugin directories inside and uncomment relevant commands in entrypoint.sh."
    fi

    if [ "$applied" = true ]; then
        touch "$BOOTSTRAP_SENTINEL"
        chown www-data:www-data "$BOOTSTRAP_SENTINEL"
    fi
}

main() {
    initial_sync_code
    sync_wsmanagesections_plugin
    chown -R www-data:www-data "$MOODLE_DIR"
    prepare_data_dir
    run_install_if_needed
    apply_post_install_config
    run_upgrade
    ensure_entrenai_user
    ensure_entrenai_external_service
    apply_bootstrap_fixtures

    exec "$@"
}

main "$@"
