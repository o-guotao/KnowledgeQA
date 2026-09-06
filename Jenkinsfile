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
                    // 生成 .env 文件
                    bat """
                        echo POSTGRES_USER=webagent > .env
                        echo POSTGRES_PASSWORD=webagent_secret >> .env
                        echo POSTGRES_DB=webagent >> .env
                        echo MINIO_ROOT_USER=minioadmin >> .env
                        echo MINIO_ROOT_PASSWORD=minioadmin123 >> .env
                        echo MINIO_BUCKET=web-agent-docs >> .env
                    """
                    
                    // 从 Jenkins 凭据注入加密密钥
                    withCredentials([string(credentialsId: 'knowledgeqa-model-config-encryption-key', variable: 'MODEL_CONFIG_ENCRYPTION_KEY')]) {
                        bat """
                            echo MODEL_CONFIG_ENCRYPTION_KEY=${MODEL_CONFIG_ENCRYPTION_KEY} >> .env
                        """
                    }
                    
                    // 预拉取所有基础镜像（使用阿里云源，然后打标准标签）
                    bat """
                        echo ========================================
                        echo 预拉取基础镜像...
                        echo ========================================
                        
                        docker pull registry.cn-hangzhou.aliyuncs.com/library/python:3.12-slim
                        docker tag registry.cn-hangzhou.aliyuncs.com/library/python:3.12-slim python:3.12-slim
                        
                        docker pull registry.cn-hangzhou.aliyuncs.com/library/node:20-alpine
                        docker tag registry.cn-hangzhou.aliyuncs.com/library/node:20-alpine node:20-alpine
                        
                        docker pull registry.cn-hangzhou.aliyuncs.com/library/nginx:1.27-alpine
                        docker tag registry.cn-hangzhou.aliyuncs.com/library/nginx:1.27-alpine nginx:1.27-alpine
                        
                        echo ========================================
                        echo 基础镜像准备完成
                        echo ========================================
                        
                        docker images | findstr python
                        docker images | findstr node
                        docker images | findstr nginx
                    """
                    
                    // 验证 Docker 环境（去掉 config -q）
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
                """
                
                if (env.HAS_ROLLBACK == 'true') {
                    echo '部署失败，尝试回滚到上一个稳定版本...'
                    bat 'docker compose up -d --no-build --remove-orphans'
                }
            }
        }
        always {
            script {
                bat 'docker compose ps'
            }
        }
    }
}
