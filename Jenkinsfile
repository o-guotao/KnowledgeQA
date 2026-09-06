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
                    // 生成 .env 基础配置
                    bat """
                        echo POSTGRES_USER=webagent > .env
                        echo POSTGRES_PASSWORD=webagent_secret >> .env
                        echo POSTGRES_DB=webagent >> .env
                        echo MINIO_ROOT_USER=minioadmin >> .env
                        echo MINIO_ROOT_PASSWORD=minioadmin123 >> .env
                        echo MINIO_BUCKET=web-agent-docs >> .env
                    """
                    
                    // 尝试从凭据注入加密密钥，如果不存在则使用默认值
                    try {
                        withCredentials([string(credentialsId: 'knowledgeqa-model-config-encryption-key', variable: 'MODEL_CONFIG_ENCRYPTION_KEY')]) {
                            bat """
                                echo MODEL_CONFIG_ENCRYPTION_KEY=${MODEL_CONFIG_ENCRYPTION_KEY} >> .env
                            """
                        }
                        echo '✅ 使用 Jenkins 凭据注入加密密钥'
                    } catch (Exception e) {
                        echo '⚠️ 未找到 knowledgeqa-model-config-encryption-key 凭据，使用默认值'
                        bat """
                            echo MODEL_CONFIG_ENCRYPTION_KEY=default-key-12345 >> .env
                        """
                    }
                    
                    // 预拉取所有基础镜像
                    bat """
                        echo ========================================
                        echo 预拉取基础镜像...
                        echo ========================================
                        
                        echo 拉取 Python 3.12-slim...
                        docker pull python:3.12-slim
                        
                        echo 拉取 Node 20-alpine...
                        docker pull node:20-alpine
                        
                        echo 拉取 Nginx 1.27-alpine...
                        docker pull nginx:1.27-alpine
                        
                        echo ========================================
                        echo 基础镜像准备完成
                        echo ========================================
                        
                        docker images | findstr python
                        docker images | findstr node
                        docker images | findstr nginx
                    """
                    
                    // 验证 Docker 环境
                    bat 'docker version && docker compose version'
                    
                    echo '✅ Preflight 检查通过'
                }
            }
        }

        stage('Build images') {
            steps {
                script {
                    bat """
                        echo ========================================
                        echo 构建 Docker 镜像...
                        echo ========================================
                        
                        docker compose build backend frontend
                        
                        echo ========================================
                        echo 镜像构建完成
                        echo ========================================
                        
                        docker images | findstr knowledgeqa
                    """
                }
            }
        }

        stage('Deploy and verify') {
            steps {
                script {
                    // 检查是否有可回滚的镜像
                    env.HAS_ROLLBACK = bat(returnStatus: true, script: 'docker image inspect knowledgeqa-backend:current >NUL 2>&1') == 0 ? 'true' : 'false'
                    
                    // 部署
                    bat 'docker compose up -d --no-build --remove-orphans'
                }
                
                // 健康检查
                script {
                    echo '等待服务启动...'
                    retry(18) {
                        sleep time: 5, unit: 'SECONDS'
                        bat 'powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing http://localhost:8000/api/healthz | Out-Null; Invoke-WebRequest -UseBasicParsing http://localhost:5173/ | Out-Null"'
                    }
                    echo '✅ 服务已启动，健康检查通过！'
                }
            }
        }
    }

    post {
        success {
            script {
                bat """
                    echo ========================================
                    echo 部署成功，标记为 current
                    echo ========================================
                    
                    docker tag knowledgeqa-backend:%IMAGE_TAG% knowledgeqa-backend:current
                    docker tag knowledgeqa-frontend:%IMAGE_TAG% knowledgeqa-frontend:current
                    
                    docker compose ps
                """
            }
        }
        failure {
            script {
                bat """
                    echo ========================================
                    echo 构建失败
                    echo ========================================
                    docker compose ps
                    docker logs web-agent-backend --tail 50 2>nul || echo 后端容器未启动
                    docker logs web-agent-frontend --tail 50 2>nul || echo 前端容器未启动
                """
                
                if (env.HAS_ROLLBACK == 'true') {
                    echo '🔄 部署失败，尝试回滚到上一个稳定版本...'
                    bat 'docker compose up -d --no-build --remove-orphans'
                }
            }
        }
        always {
            script {
                bat """
                    echo ========================================
                    echo 最终容器状态
                    echo ========================================
                    docker compose ps
                """
            }
        }
    }
}
