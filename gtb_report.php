<?php
/**
 * GTB LB install report receiver.
 *
 * Upload this file to thesocialclub.co.in as /gtb/report.php (or any path;
 * just match REPORT_URL in install-lb). It accepts a POST from install-lb
 * with a small JSON-ish set of fields, checks a shared token, and appends
 * one JSON line to a log file kept outside the web root.
 *
 * Deploy steps:
 *   1. Upload this file as report.php next to the included .htaccess
 *      (or merge the deny rule into an existing .htaccess in that folder).
 *   2. Set REPORT_TOKEN below to the same 32-hex value baked into install-lb.
 *   3. Set LOG_FILE to a path outside the web root (preferred) or rely on
 *      the .htaccess "deny from all" if it must stay inside the web root.
 *   4. Make sure the web server user can write LOG_FILE.
 */

// Must match REPORT_TOKEN in install-lb.
define('REPORT_TOKEN', '68b58d0ea965b5a55a02dab2cf80b1a9');

// Outside the web root is strongly preferred. If that is not possible on
// this host, leave it under this folder; the shipped .htaccess denies all
// HTTP access to *.log here.
define('LOG_FILE', __DIR__ . '/gtb-install-report.log');

define('RATE_LIMIT_FILE', __DIR__ . '/.gtb-rate-limit');
define('RATE_LIMIT_WINDOW', 60);     // seconds
define('RATE_LIMIT_MAX', 20);        // requests per window, per process (simple, file-based)

define('MAX_FIELD_LEN', 256);

function bad_request($code, $msg) {
    http_response_code($code);
    header('Content-Type: text/plain');
    echo $msg . "\n";
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    bad_request(405, 'POST only');
}

$token = isset($_SERVER['HTTP_X_GTB_TOKEN']) ? $_SERVER['HTTP_X_GTB_TOKEN'] : '';
if (!is_string($token) || !hash_equals(REPORT_TOKEN, $token)) {
    bad_request(403, 'forbidden');
}

// Very small rate limit: a counter file keyed by the current window.
// Not a substitute for a real rate limiter, but enough to blunt accidental
// floods from a mis-scripted install run.
$window = intdiv(time(), RATE_LIMIT_WINDOW);
$rateData = @file_get_contents(RATE_LIMIT_FILE);
$rateWindow = null;
$rateCount = 0;
if ($rateData !== false) {
    $parts = explode(':', trim($rateData), 2);
    if (count($parts) === 2) {
        $rateWindow = (int)$parts[0];
        $rateCount = (int)$parts[1];
    }
}
if ($rateWindow !== $window) {
    $rateWindow = $window;
    $rateCount = 0;
}
$rateCount++;
@file_put_contents(RATE_LIMIT_FILE, $rateWindow . ':' . $rateCount, LOCK_EX);
if ($rateCount > RATE_LIMIT_MAX) {
    bad_request(429, 'rate limited');
}

function clean_field($value) {
    if (!is_string($value)) return '';
    $value = substr($value, 0, MAX_FIELD_LEN);
    // Strip control characters; keep it to plain printable text.
    $value = preg_replace('/[\x00-\x1F\x7F]/', '', $value);
    return $value;
}

$fields = [
    'ip'                => clean_field($_POST['ip'] ?? ''),
    'hostname'          => clean_field($_POST['hostname'] ?? ''),
    'ubuntu_version'    => clean_field($_POST['ubuntu_version'] ?? ''),
    'installer_version' => clean_field($_POST['installer_version'] ?? ''),
    'timestamp'         => clean_field($_POST['timestamp'] ?? ''),
];

if ($fields['ip'] === '' || $fields['hostname'] === '') {
    bad_request(400, 'missing required fields');
}

$entry = [
    'received_at' => date('c'),
    'remote_addr' => $_SERVER['REMOTE_ADDR'] ?? '',
] + $fields;

$line = json_encode($entry, JSON_UNESCAPED_SLASHES) . "\n";
$fh = @fopen(LOG_FILE, 'ab');
if ($fh === false) {
    bad_request(500, 'could not write log');
}
flock($fh, LOCK_EX);
fwrite($fh, $line);
flock($fh, LOCK_UN);
fclose($fh);

http_response_code(204);
