// ============================================================
// BharatAlpha — Jenkinsfile
// ============================================================
// 7-stage pipeline:
//   1. Pre-Flight Check    — workspace, disk, Docker daemon
//   2. Validate Env        — required credentials present
//   3. API Connectivity    — Angel One auth + Anthropic ping
//   4. Clean Workspace     — remove old images, containers
//   5. Build Image         — docker build (multi-stage)
//   6. Deploy Container    — docker run with volumes + logging
//   7. Verify Health       — Streamlit health endpoint
//
// Required Jenkins credentials (Secret Text):
//   ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_MPIN, ANGEL_TOTP_SECRET
//   ANTHROPIC_API_KEY, SERPER_API_KEY
// ============================================================

pipeline {

    agent any

    // ── Environment ─────────────────────────────────────────
    environment {
        APP_NAME        = "bharatalpha"
        IMAGE_NAME      = "bharatalpha"
        IMAGE_TAG       = "${BUILD_NUMBER}"
        CONTAINER_NAME  = "bharatalpha_app"
        APP_PORT        = "8501"
        HEALTH_URL      = "http://localhost:${APP_PORT}/_stcore/health"

        // Writable directories inside container — must be chmod 777
        // (matches Dockerfile; Jenkins may run as different UID)
        OUTPUT_VOLUME   = "bharatalpha_output"
        WATCHLIST_VOLUME = "bharatalpha_watchlist"

        // Deployment log driver
        LOG_MAX_SIZE    = "50m"
        LOG_MAX_FILE    = "5"

        // Slack/email notifications (set to empty to disable)
        NOTIFY_EMAIL    = ""   // e.g. "team@company.com"
    }

    // ── Options ──────────────────────────────────────────────
    options {
        buildDiscarder(logRotator(numToKeepStr: '10'))
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds()
        timestamps()
    }

    // ── Parameters (optional manual overrides) ───────────────
    parameters {
        booleanParam(
            name:         'SKIP_API_CHECK',
            defaultValue: false,
            description:  'Skip Angel One API connectivity test (use if market is closed)'
        )
        booleanParam(
            name:         'FORCE_REBUILD',
            defaultValue: false,
            description:  'Force Docker build with --no-cache'
        )
    }

    // ── Stages ───────────────────────────────────────────────
    stages {

        // ── Stage 1: Pre-Flight ──────────────────────────────
        stage('Pre-Flight Check') {
            steps {
                echo "═══════════════════════════════════════════"
                echo "  BharatAlpha CI/CD — Build #${BUILD_NUMBER}"
                echo "  Branch: ${env.BRANCH_NAME ?: 'N/A'}"
                echo "  Started: ${new Date()}"
                echo "═══════════════════════════════════════════"

                script {
                    // Confirm Docker daemon is reachable
                    sh 'docker info > /dev/null 2>&1 || (echo "ERROR: Docker daemon not running" && exit 1)'

                    // Confirm minimum disk space (2 GB free)
                    sh '''
                        FREE_KB=$(df /var/lib/docker | tail -1 | awk '{print $4}')
                        FREE_GB=$((FREE_KB / 1048576))
                        echo "Free disk space: ${FREE_GB} GB"
                        if [ "$FREE_GB" -lt 2 ]; then
                            echo "ERROR: Less than 2 GB free on Docker disk. Aborting."
                            exit 1
                        fi
                    '''

                    // Confirm src/ and config/ directories exist in workspace
                    sh '''
                        test -d src     || (echo "ERROR: src/ not found in workspace"    && exit 1)
                        test -d config  || (echo "ERROR: config/ not found in workspace" && exit 1)
                        test -f app.py  || (echo "ERROR: app.py not found in workspace"  && exit 1)
                        test -f Dockerfile || (echo "ERROR: Dockerfile not found"         && exit 1)
                        test -f requirements.txt || (echo "ERROR: requirements.txt missing" && exit 1)
                        echo "✓ Workspace structure validated"
                    '''

                    // Quick Python syntax check on core modules
                    sh '''
                        python3 -c "import ast" 2>/dev/null || python -c "import ast"
                        for f in src/utils.py src/tools.py src/crew.py app.py; do
                            python3 -c "
import ast, sys
with open('$f') as fh:
    try:
        ast.parse(fh.read())
        print('  ✓ Syntax OK: $f')
    except SyntaxError as e:
        print('  ✗ Syntax ERROR in $f:', e)
        sys.exit(1)
" 2>/dev/null || python -c "
import ast, sys
with open('$f') as fh:
    try:
        ast.parse(fh.read())
        print('  OK: $f')
    except SyntaxError as e:
        print('  ERROR in $f:', e)
        sys.exit(1)
"
                        done
                        echo "✓ Python syntax checks passed"
                    '''
                }
            }
        }

        // ── Stage 2: Validate Environment ────────────────────
        stage('Validate Env') {
            steps {
                script {
                    withCredentials([
                        string(credentialsId: 'ANGEL_API_KEY',      variable: 'ANGEL_API_KEY'),
                        string(credentialsId: 'ANGEL_CLIENT_ID',    variable: 'ANGEL_CLIENT_ID'),
                        string(credentialsId: 'ANGEL_MPIN',         variable: 'ANGEL_MPIN'),
                        string(credentialsId: 'ANGEL_TOTP_SECRET',  variable: 'ANGEL_TOTP_SECRET'),
                        string(credentialsId: 'ANTHROPIC_API_KEY',  variable: 'ANTHROPIC_API_KEY'),
                        string(credentialsId: 'SERPER_API_KEY',     variable: 'SERPER_API_KEY'),
                    ]) {
                        sh '''
                            echo "Validating required credentials..."

                            MISSING=0
                            check_var() {
                                if [ -z "$1" ]; then
                                    echo "  ✗ MISSING: $2"
                                    MISSING=1
                                else
                                    echo "  ✓ SET:     $2"
                                fi
                            }

                            check_var "$ANGEL_API_KEY"     "ANGEL_API_KEY"
                            check_var "$ANGEL_CLIENT_ID"   "ANGEL_CLIENT_ID"
                            check_var "$ANGEL_MPIN"        "ANGEL_MPIN"
                            check_var "$ANGEL_TOTP_SECRET" "ANGEL_TOTP_SECRET"
                            check_var "$ANTHROPIC_API_KEY" "ANTHROPIC_API_KEY"
                            check_var "$SERPER_API_KEY"    "SERPER_API_KEY"

                            if [ "$MISSING" -eq 1 ]; then
                                echo ""
                                echo "ERROR: One or more required credentials are missing."
                                echo "Add them via Jenkins > Manage Credentials > Global."
                                exit 1
                            fi

                            echo ""
                            echo "✓ All credentials validated"
                        '''
                    }
                }
            }
        }

        // ── Stage 3: API Connectivity ─────────────────────────
        // Added for BharatAlpha — no point building if primary
        // data source (Angel One) is unreachable or misconfigured.
        stage('API Connectivity') {
            when {
                expression { return !params.SKIP_API_CHECK }
            }
            steps {
                script {
                    withCredentials([
                        string(credentialsId: 'ANGEL_API_KEY',      variable: 'ANGEL_API_KEY'),
                        string(credentialsId: 'ANGEL_CLIENT_ID',    variable: 'ANGEL_CLIENT_ID'),
                        string(credentialsId: 'ANGEL_MPIN',         variable: 'ANGEL_MPIN'),
                        string(credentialsId: 'ANGEL_TOTP_SECRET',  variable: 'ANGEL_TOTP_SECRET'),
                        string(credentialsId: 'ANTHROPIC_API_KEY',  variable: 'ANTHROPIC_API_KEY'),
                    ]) {
                        sh '''
                            echo "Testing Angel One SmartAPI authentication..."

                            # Run auth test inside a temporary container using the
                            # same Python environment as the final image, so we catch
                            # auth failures BEFORE committing to a full build.
                            docker run --rm \
                                -e ANGEL_API_KEY="$ANGEL_API_KEY" \
                                -e ANGEL_CLIENT_ID="$ANGEL_CLIENT_ID" \
                                -e ANGEL_MPIN="$ANGEL_MPIN" \
                                -e ANGEL_TOTP_SECRET="$ANGEL_TOTP_SECRET" \
                                -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
                                -v "$(pwd)":/workspace \
                                -w /workspace \
                                python:3.11-slim \
                                bash -c "
                                    pip install SmartApi-python pyotp requests python-dotenv --quiet 2>/dev/null
                                    python3 -c \"
import os, sys
os.environ.setdefault('ANGEL_API_KEY',     '$ANGEL_API_KEY')
os.environ.setdefault('ANGEL_CLIENT_ID',   '$ANGEL_CLIENT_ID')
os.environ.setdefault('ANGEL_MPIN',        '$ANGEL_MPIN')
os.environ.setdefault('ANGEL_TOTP_SECRET', '$ANGEL_TOTP_SECRET')

try:
    import pyotp
    from SmartApi import SmartConnect
    api = SmartConnect(api_key=os.environ['ANGEL_API_KEY'])
    totp_secret = os.environ['ANGEL_TOTP_SECRET']
    totp = pyotp.TOTP(totp_secret).now()
    data = api.generateSession(
        os.environ['ANGEL_CLIENT_ID'],
        os.environ['ANGEL_MPIN'],
        totp
    )
    if data and data.get('status') is True:
        print('✓ Angel One auth: SUCCESS')
        sys.exit(0)
    else:
        print('✗ Angel One auth FAILED:', data.get('message', 'unknown error'))
        sys.exit(1)
except Exception as e:
    print('✗ Angel One auth EXCEPTION:', str(e))
    sys.exit(1)
\"
                                " 2>&1

                            echo ""
                            echo "✓ API connectivity verified"
                        '''

                        // Anthropic API reachability check (lightweight)
                        sh '''
                            echo "Testing Anthropic API reachability..."
                            HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
                                -H "x-api-key: $ANTHROPIC_API_KEY" \
                                -H "anthropic-version: 2023-06-01" \
                                https://api.anthropic.com/v1/models 2>/dev/null || echo "000")

                            if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "401" ]; then
                                # 200 = valid key, 401 = reachable but key format issue
                                # Both mean the endpoint is reachable
                                echo "✓ Anthropic API endpoint reachable (HTTP $HTTP_CODE)"
                            else
                                echo "⚠ Anthropic API returned HTTP $HTTP_CODE — network issue possible"
                                echo "  Continuing build (will fail at runtime if key is invalid)"
                            fi
                        '''
                    }
                }
            }
            post {
                failure {
                    echo """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  API CONNECTIVITY STAGE FAILED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Angel One SmartAPI authentication failed.
  Possible causes:
    1. ANGEL_MPIN or ANGEL_TOTP_SECRET incorrect
    2. Angel One session already active (concurrent login)
    3. Market is closed / Angel One maintenance window
    4. Network egress blocked from Jenkins host

  To bypass for a closed-market deploy:
    Re-run with: SKIP_API_CHECK = true
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
                }
            }
        }

        // ── Stage 4: Clean ────────────────────────────────────
        stage('Clean') {
            steps {
                script {
                    sh '''
                        echo "Stopping and removing existing container..."
                        docker stop ${CONTAINER_NAME} 2>/dev/null || true
                        docker rm   ${CONTAINER_NAME} 2>/dev/null || true
                        echo "✓ Container cleaned"

                        echo "Removing old images (keep last 2 builds)..."
                        docker images ${IMAGE_NAME} --format "{{.ID}} {{.Tag}}" \
                            | sort -k2 -rn \
                            | tail -n +3 \
                            | awk '{print $1}' \
                            | xargs -r docker rmi -f 2>/dev/null || true
                        echo "✓ Old images pruned"

                        # Remove dangling images to reclaim disk
                        docker image prune -f 2>/dev/null || true
                        echo "✓ Dangling images pruned"
                    '''
                }
            }
        }

        // ── Stage 5: Build Image ──────────────────────────────
        stage('Build Image') {
            steps {
                script {
                    def buildArgs = params.FORCE_REBUILD ? '--no-cache' : ''

                    sh """
                        echo "Building BharatAlpha Docker image..."
                        echo "  Tag:   ${IMAGE_NAME}:${IMAGE_TAG}"
                        echo "  Args:  ${buildArgs ?: '(cached)'}"
                        echo ""

                        docker build ${buildArgs} \
                            -t ${IMAGE_NAME}:${IMAGE_TAG} \
                            -t ${IMAGE_NAME}:latest \
                            --label "build.number=${BUILD_NUMBER}" \
                            --label "build.timestamp=\$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
                            --label "git.branch=${env.BRANCH_NAME ?: 'unknown'}" \
                            .

                        echo ""
                        echo "✓ Image built: ${IMAGE_NAME}:${IMAGE_TAG}"
                    """

                    // Verify key directories exist in the built image
                    sh """
                        echo "Verifying image structure..."
                        docker run --rm ${IMAGE_NAME}:${IMAGE_TAG} \
                            bash -c "
                                test -d /app/src     && echo '  ✓ /app/src'     || (echo '  ✗ /app/src missing'     && exit 1)
                                test -d /app/config  && echo '  ✓ /app/config'  || (echo '  ✗ /app/config missing'  && exit 1)
                                test -f /app/app.py  && echo '  ✓ /app/app.py'  || (echo '  ✗ /app/app.py missing'  && exit 1)
                                test -d /app/output  && echo '  ✓ /app/output'  || (echo '  ✗ /app/output missing'  && exit 1)
                                echo '  ✓ Image structure verified'
                            "
                    """

                    // Verify Python imports work inside the image
                    sh """
                        echo "Verifying Python imports..."
                        docker run --rm ${IMAGE_NAME}:${IMAGE_TAG} \
                            python -c "
from src.utils import get_logger, DataQualityTracker, composite_score
from src.crew  import BharatAlphaCrew
import streamlit
import crewai
print('  ✓ All imports resolved')
print(f'  ✓ crewai {crewai.__version__}')
print(f'  ✓ streamlit {streamlit.__version__}')
"
                    """
                }
            }
        }

        // ── Stage 6: Deploy Container ─────────────────────────
        stage('Deploy') {
            steps {
                script {
                    withCredentials([
                        string(credentialsId: 'ANGEL_API_KEY',      variable: 'ANGEL_API_KEY'),
                        string(credentialsId: 'ANGEL_CLIENT_ID',    variable: 'ANGEL_CLIENT_ID'),
                        string(credentialsId: 'ANGEL_MPIN',         variable: 'ANGEL_MPIN'),
                        string(credentialsId: 'ANGEL_TOTP_SECRET',  variable: 'ANGEL_TOTP_SECRET'),
                        string(credentialsId: 'ANTHROPIC_API_KEY',  variable: 'ANTHROPIC_API_KEY'),
                        string(credentialsId: 'SERPER_API_KEY',     variable: 'SERPER_API_KEY'),
                    ]) {
                        sh """
                            echo "Creating persistent Docker volumes (if not exist)..."
                            docker volume create ${OUTPUT_VOLUME}   2>/dev/null || true
                            docker volume create ${WATCHLIST_VOLUME} 2>/dev/null || true
                            echo "✓ Volumes ready"

                            echo ""
                            echo "Deploying BharatAlpha container..."

                            docker run -d \
                                --name  ${CONTAINER_NAME} \
                                --restart unless-stopped \
                                -p ${APP_PORT}:8501 \
                                -e ANGEL_API_KEY="${ANGEL_API_KEY}" \
                                -e ANGEL_CLIENT_ID="${ANGEL_CLIENT_ID}" \
                                -e ANGEL_MPIN="${ANGEL_MPIN}" \
                                -e ANGEL_TOTP_SECRET="${ANGEL_TOTP_SECRET}" \
                                -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}" \
                                -e SERPER_API_KEY="${SERPER_API_KEY}" \
                                -e PYTHONUNBUFFERED=1 \
                                -e STREAMLIT_SERVER_PORT=8501 \
                                -e STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
                                -e STREAMLIT_SERVER_HEADLESS=true \
                                -e STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
                                -v ${OUTPUT_VOLUME}:/app/output \
                                -v ${WATCHLIST_VOLUME}:/app/watchlist \
                                --log-driver json-file \
                                --log-opt max-size=${LOG_MAX_SIZE} \
                                --log-opt max-file=${LOG_MAX_FILE} \
                                --memory="1.5g" \
                                --memory-swap="2g" \
                                --cpus="1.5" \
                                ${IMAGE_NAME}:${IMAGE_TAG}

                            echo ""
                            echo "✓ Container deployed: ${CONTAINER_NAME}"
                            echo "  Image:   ${IMAGE_NAME}:${IMAGE_TAG}"
                            echo "  Port:    ${APP_PORT}"
                            echo "  Output:  volume/${OUTPUT_VOLUME}"
                        """
                    }
                }
            }
        }

        // ── Stage 7: Verify Health ────────────────────────────
        stage('Verify Health') {
            steps {
                script {
                    sh '''
                        echo "Waiting for Streamlit to initialise (30s)..."
                        sleep 30

                        echo "Checking health endpoint..."
                        ATTEMPTS=0
                        MAX_ATTEMPTS=6

                        until curl -sf ${HEALTH_URL} > /dev/null 2>&1; do
                            ATTEMPTS=$((ATTEMPTS + 1))
                            if [ "$ATTEMPTS" -ge "$MAX_ATTEMPTS" ]; then
                                echo ""
                                echo "ERROR: Health check failed after ${MAX_ATTEMPTS} attempts."
                                echo ""
                                echo "Container logs (last 50 lines):"
                                docker logs --tail=50 ${CONTAINER_NAME} 2>&1 || true
                                exit 1
                            fi
                            echo "  Attempt ${ATTEMPTS}/${MAX_ATTEMPTS} — retrying in 10s..."
                            sleep 10
                        done

                        echo "✓ Health check passed: ${HEALTH_URL}"
                    '''

                    // Print deployment summary
                    sh '''
                        echo ""
                        echo "═══════════════════════════════════════════"
                        echo "  ✓ BHARATALPHA DEPLOYED SUCCESSFULLY"
                        echo "═══════════════════════════════════════════"
                        echo "  URL:       http://$(curl -s http://169.254.169.254/latest/meta-data/public-hostname 2>/dev/null || hostname):${APP_PORT}"
                        echo "  Container: ${CONTAINER_NAME}"
                        echo "  Image:     ${IMAGE_NAME}:${IMAGE_TAG}"
                        echo "  Build:     #${BUILD_NUMBER}"
                        echo "  Time:      $(date)"
                        echo "═══════════════════════════════════════════"

                        echo ""
                        echo "Container resource usage:"
                        docker stats ${CONTAINER_NAME} --no-stream --format \
                            "  CPU: {{.CPUPerc}}  |  MEM: {{.MemUsage}}  |  NET: {{.NetIO}}"
                    '''
                }
            }
        }

    } // end stages

    // ── Post Actions ─────────────────────────────────────────
    post {
        success {
            echo "✓ Pipeline completed successfully — Build #${BUILD_NUMBER}"
        }

        failure {
            script {
                echo "✗ Pipeline FAILED — Build #${BUILD_NUMBER}"

                // Dump container logs on failure for easier debugging
                sh '''
                    if docker ps -a --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
                        echo ""
                        echo "Container logs (last 80 lines):"
                        docker logs --tail=80 ${CONTAINER_NAME} 2>&1 || true
                    fi
                '''

                // Send email notification if configured
                if (env.NOTIFY_EMAIL?.trim()) {
                    mail(
                        to:      env.NOTIFY_EMAIL,
                        subject: "[BharatAlpha] Build #${BUILD_NUMBER} FAILED",
                        body:    """
BharatAlpha CI/CD pipeline failed.

Build:  #${BUILD_NUMBER}
Branch: ${env.BRANCH_NAME ?: 'N/A'}
Time:   ${new Date()}

Review the Jenkins console output for details:
${env.BUILD_URL}console
"""
                    )
                }
            }
        }

        aborted {
            echo "⚠ Pipeline aborted — Build #${BUILD_NUMBER}"
        }

        always {
            // Clean up the API connectivity test container if it
            // was left behind by an unexpected failure
            sh 'docker rm -f bharatalpha_api_test 2>/dev/null || true'
        }
    }

} // end pipeline