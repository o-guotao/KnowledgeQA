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
          if (isUnix()) {
            sh 'docker version && docker compose version && docker compose config -q'
          } else {
            bat 'docker version && docker compose version && docker compose config -q'
          }
        }
      }
    }

    stage('Build images') {
      steps {
        script {
          if (isUnix()) {
            sh 'docker compose build backend frontend'
          } else {
            bat 'docker compose build backend frontend'
          }
        }
      }
    }

    stage('Deploy and verify') {
      steps {
        withCredentials([string(credentialsId: 'knowledgeqa-model-config-encryption-key', variable: 'MODEL_CONFIG_ENCRYPTION_KEY')]) {
          script {
            if (isUnix()) {
              env.HAS_ROLLBACK = sh(returnStatus: true, script: 'docker image inspect knowledgeqa-backend:current >/dev/null 2>&1') == 0 ? 'true' : 'false'
              sh 'docker compose up -d --no-build --remove-orphans'
            } else {
              env.HAS_ROLLBACK = bat(returnStatus: true, script: 'docker image inspect knowledgeqa-backend:current >NUL 2>&1') == 0 ? 'true' : 'false'
              bat 'docker compose up -d --no-build --remove-orphans'
            }
          }
        }
        script {
          retry(18) {
            sleep time: 5, unit: 'SECONDS'
            if (isUnix()) {
              sh 'curl --fail --silent --show-error http://localhost:8000/api/healthz && curl --fail --silent --show-error http://localhost:5173/'
            } else {
              bat 'powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing http://localhost:8000/api/healthz | Out-Null; Invoke-WebRequest -UseBasicParsing http://localhost:5173/ | Out-Null"'
            }
          }
        }
      }
    }
  }

  post {
    success {
      script {
        if (isUnix()) {
          sh 'docker tag knowledgeqa-backend:${IMAGE_TAG} knowledgeqa-backend:current && docker tag knowledgeqa-frontend:${IMAGE_TAG} knowledgeqa-frontend:current'
        } else {
          bat 'docker tag knowledgeqa-backend:%IMAGE_TAG% knowledgeqa-backend:current && docker tag knowledgeqa-frontend:%IMAGE_TAG% knowledgeqa-frontend:current'
        }
      }
    }
    failure {
      script {
        if (env.HAS_ROLLBACK == 'true') {
          echo 'Deployment failed; restoring the last known-good application images.'
          withCredentials([string(credentialsId: 'knowledgeqa-model-config-encryption-key', variable: 'MODEL_CONFIG_ENCRYPTION_KEY')]) {
            if (isUnix()) {
              withEnv(['IMAGE_TAG=current']) { sh 'docker compose up -d --no-build --remove-orphans' }
            } else {
              withEnv(['IMAGE_TAG=current']) { bat 'docker compose up -d --no-build --remove-orphans' }
            }
          }
        }
      }
    }
    always {
      script {
        if (isUnix()) {
          sh 'docker compose ps'
        } else {
          bat 'docker compose ps'
        }
      }
    }
  }
}
