package util

import (
	//"bufio"
	//"bytes"
	"errors"
	"fmt"
	//"log"
	"net"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	//"syscall"
	"time"
	//"github.com/m-lab/go/uuid"
)

// The new test output filename is joint of hostname, server boot time, and socker TCO cookie.
// like: pboothe2.nyc.corp.google.com_1548788619_00000000000084FF
var IGNORE_IPV4_NETS = []string{"127.", "128.112.139.", "::ffff:127.0.0.1"}

func MakeTestFilename(cookie string) (string, error) {
	stat, err := os.Stat("/proc")
	if err != nil {
		return "", err
	}
	hostname, err := exec.Command("hostname").Output()
	out := string(hostname)
	out = strings.TrimSuffix(out, "\n")

	// cookie is a hexdecimal string
	result, _ := strconv.ParseUint(cookie, 16, 64)
	return fmt.Sprintf("%s_%d_%016X", out, stat.ModTime().Unix(), uint64(result)), nil
}

func ParseIPAndPort(input string) (string, int, error) {
	seperator := strings.LastIndex(input, ":")
	if seperator == -1 {
		return "", 0, errors.New("cannot parse IP and port correctly")
	}
	IPStr := input[0:seperator]
	if IPStr[0] == '[' {
		IPStr = IPStr[1 : len(IPStr)-1]
	}
	for _, prefix := range IGNORE_IPV4_NETS {
		if strings.HasPrefix(IPStr, prefix) {
			return "", 0, errors.New("ignore this IP address")
		}
	}
	outputIP := net.ParseIP(IPStr)
	if outputIP == nil {
		return "", 0, errors.New("invalid IP address")
	}

	port, err := strconv.Atoi(input[seperator+1:])
	if err != nil {
		return "", 0, errors.New("invalid IP port")
	}
	return IPStr, port, nil
}

func ParseCookie(input string) (string, error) {
	if !strings.HasPrefix(input, "sk:") {
		return "", errors.New("no cookie")
	}
	return input[3:], nil
}

// CreateTimePath return a string with date in format yyyy/mm/dd/
func CreateTimePath(prefix string) string {
	currentTime := time.Now().Format("2006-01-02")
	date := strings.Split(currentTime, "-")
	if len(date) != 3 {
		return ""
	}
	if _, err := os.Stat(prefix + date[0]); os.IsNotExist(err) {
		os.Mkdir(prefix+date[0], 0700)
	}
	if _, err := os.Stat(prefix + date[0] + "/" + date[1]); os.IsNotExist(err) {
		os.Mkdir(prefix+date[0]+"/"+date[1], 0700)
	}
	if _, err := os.Stat(prefix + date[0] + "/" + date[1] + "/" + date[2]); os.IsNotExist(err) {
		os.Mkdir(prefix+date[0]+"/"+date[1]+"/"+date[2], 0700)
	}
	return prefix + date[0] + "/" + date[1] + "/" + date[2] + "/"
}

// ///////////////////////////////////////////////////////////////////////

// Do not traceroute to an IP more than once in this many seconds
var IP_CACHE_TIME_SECONDS = 120

var MAX_CACHE_ENTRY = 1000

type RecentIPCache struct {
	cache map[string]int64
	mu    sync.Mutex
}

func (m *RecentIPCache) New() {
	m = &RecentIPCache{cache: make(map[string]int64, 1000)}
	go func() {
		for now := range time.Tick(time.Second) {
			for k, v := range m.cache {
				if now.Unix()-v > int64(IP_CACHE_TIME_SECONDS) {
					m.mu.Lock()
					delete(m.cache, k)
					m.mu.Unlock()
				}
			}
		}
	}()
	return
}

func (m *RecentIPCache) Len() int {
	return len(m.cache)
}

func (m *RecentIPCache) Add(ip string) {
	_, ok := m.cache[ip]
	if !ok {
		m.mu.Lock()
		if m.cache == nil {
			m.cache = make(map[string]int64)
		}
		m.cache[ip] = time.Now().Unix()
		m.mu.Unlock()
	}
}

func (m *RecentIPCache) Has(ip string) bool {
	m.mu.Lock()
	defer m.mu.Unlock()
	_, ok := m.cache[ip]
	return ok
}
