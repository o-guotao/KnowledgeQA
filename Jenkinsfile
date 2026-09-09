pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
    }

    environment {
        COMPOSE_PROJECT_NAME = 'knowledgeqa'
        IMAGE_TAG = "build-${BUILD_NUMBER}"
    }

    stages {
        stage('Preflight') {
            steps {
                script {
                    // 检查 .env 文件是否存在，如果不存在则创建（Linux/sh 版）
                    sh '''
                        if [ ! -f .env ]; then
                            echo "========================================"
                            echo "创建 .env 文件..."
                            echo "========================================"
                            cat > .env <<'ENVEOF'
POSTGRES_USER=webagent
POSTGRES_PASSWORD=webagent_secret
POSTGRES_DB=webagent
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin123
MINIO_BUCKET=web-agent-docs
MODEL_CONFIG_ENCRYPTION_KEY=jFmL8108VYDECAhGp4fEs4q2b4boQ7f32pzKQCxlqt0=
ENVEOF
                        else
                            echo "========================================"
                            echo ".env 文件已存在，跳过创建"
                            echo "========================================"
                            cat .env
                        fi
                    '''

                    // 预拉取所有基础镜像
                    sh '''
                        echo "========================================"
                        echo "预拉取基础镜像..."
                        echo "========================================"

                        echo "拉取 Python 3.12-slim..."
                        docker pull python:3.12-slim

                        echo "拉取 Node 20-alpine..."
                        docker pull node:20-alpine

                        echo "拉取 Nginx 1.27-alpine..."
                        docker pull nginx:1.27-alpine

                        echo "========================================"
                        echo "基础镜像准备完成"
                        echo "========================================"

                        docker images | grep -E 'python|node|nginx' || true
                    '''

                    // 验证 Docker 环境
                    sh 'docker version && docker compose version'

                    echo '✅ Preflight 检查通过'
                }
            }
        }

        stage('Build images') {
            steps {
                script {
                    sh '''
                        echo "========================================"
                        echo "构建 Docker 镜像..."
                        echo "========================================"

                        docker compose build backend frontend

                        echo "========================================"
                        echo "镜像构建完成"
                        echo "========================================"

                        docker images | grep knowledgeqa || true
                    '''
                }
            }
        }

        stage('Deploy and verify') {
            steps {
                script {
                    // 检查是否有可回滚的镜像
                    def rollbackExists = sh(returnStatus: true, script: 'docker image inspect knowledgeqa-backend:current >/dev/null 2>&1') == 0
                    env.HAS_ROLLBACK = rollbackExists ? 'true' : 'false'

                    // 部署（数据均为命名卷；本流水线启用的服务无相对路径 bind mount）
                    sh 'docker compose up -d --no-build --remove-orphans'

                    echo '等待服务启动...'
                    sleep time: 30, unit: 'SECONDS'

                    // 健康检查：轮询容器自身 healthcheck（backend/frontend 的 compose 内已定义）
                    retry(18) {
                        script {
                            sleep time: 10, unit: 'SECONDS'
                            def bst = sh(returnStatus: true, script: "docker inspect -f '{{.State.Health.Status}}' web-agent-backend 2>/dev/null")
                            def fst = sh(returnStatus: true, script: "docker inspect -f '{{.State.Health.Status}}' web-agent-frontend 2>/dev/null")
                            def bs = (bst == 0) ? sh(script: "docker inspect -f '{{.State.Health.Status}}' web-agent-backend", returnStdout: true).trim() : 'missing'
                            def fs = (fst == 0) ? sh(script: "docker inspect -f '{{.State.Health.Status}}' web-agent-frontend", returnStdout: true).trim() : 'missing'
                            echo "health backend=${bs} frontend=${fs}"
                            if (bs == 'healthy' && fs == 'healthy') {
                                echo '✅ 服务已启动，健康检查通过！'
                            } else {
                                error "等待服务就绪... (backend=${bs}, frontend=${fs})"
                            }
                        }
                    }
                }
            }
        }
    }

    post {
        success {
            script {
                sh """
                    echo "========================================"
                    echo "部署成功，标记为 current"
                    echo "========================================"

                    docker tag knowledgeqa-backend:${env.IMAGE_TAG} knowledgeqa-backend:current
                    docker tag knowledgeqa-frontend:${env.IMAGE_TAG} knowledgeqa-frontend:current

                    docker compose ps
                """
            }
        }
        failure {
            script {
                sh """
                    echo "========================================"
                    echo "构建失败"
                    echo "========================================"
                    docker compose ps || true
                    docker logs web-agent-backend --tail 50 2>/dev/null || echo '后端容器未启动'
                    docker logs web-agent-frontend --tail 50 2>/dev/null || echo '前端容器未启动'
                """

                if (env.HAS_ROLLBACK == 'true') {
                    echo '🔄 部署失败，尝试回滚到上一个稳定版本...'
                    sh 'docker compose up -d --no-build --remove-orphans'
                }
            }
        }
        always {
            script {
                sh """
                    echo "========================================"
                    echo "最终容器状态"
                    echo "========================================"
                    docker compose ps || true
                """
            }
        }
    }
}
